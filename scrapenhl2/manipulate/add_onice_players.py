"""
Add on-ice players to a file by specifying filename and columns from which to infer time elapsed in game.
"""

import pandas as pd

from scrapenhl2.scrape import schedules, parse_toi, autoupdate, team_info, teams, players
from scrapenhl2.scrape import general_helpers as helpers

def add_players_to_file(filename, focus_team, season=None, gamecol='Game', periodcol='Period', timecol='Time',
                        time_format='Elapsed', update_data=False, player_output='names'):
    """
    Adds names of on-ice players to the end of each line. You cannot necessarily trust results when times coincide
    with faceoff or stoppage times.

    :param filename: str, the file to read. Will save output as this filename but ending in "on-ice.csv"

    :return: nothing
    """
    if update_data:
        autoupdate.autoupdate()
    if season is None:
        season = schedules.get_current_season()

    df = _read_tracking_file(filename)
    df = _add_times_to_file(df, periodcol, timecol, time_format)
    df = _add_onice_players_to_df(df, focus_team, season, gamecol, player_output)
    _write_tracking_file(df, filename)


def _write_tracking_file(df, original_filename):
    """
    Uses the original filename to create a new filename, and writes that to file.

    :param df: dataframe
    :param original_filename: str

    :return: nothing. df written to original_filename ending in "on-ice.csv
    """

    new_filename = original_filename[:original_filename.rfind('.')] + '_on-ice.csv'
    df.to_csv(new_filename, index=False)


def _add_onice_players_to_df(df, focus_team, season, gamecol, player_output):
    """
    Uses the _Secs column in df, the season, and the gamecol to join onto on-ice players.

    :param df: dataframe
    :param focus_team: str or int, team to focus on. Its players will be listed in first in sheet.
    :param season: int, the season
    :param gamecol: str, the column with game IDs
    :param player_output: str, use 'names' or 'nums'. Currently only 'names' is supported.

    :return: dataframe with team and opponent players
    """

    teamid = team_info.team_as_id(focus_team)
    teamname = team_info.team_as_str(focus_team)

    toi = teams.get_team_toi(season, focus_team).rename(columns={'Time': '_Secs'})
    toi = toi[['Game', '_Secs', 'Team1', 'Team2', 'Team3', 'Team4', 'Team5',
               'Opp1', 'Opp2', 'Opp3', 'Opp4', 'Opp5']]

    # Now convert to names or numbers
    for col in toi.columns[-10:]:
        toi.loc[:, col] = players.playerlst_as_str(toi[col])
        if player_output == 'nums':
            pass  # TODO

    # Rename columns
    toi = toi.rename(columns={col: '{0:s}{1:s}'.format(focus_team, col[-1])
                              for col in toi.columns if len(col) >= 4 and col[:4] == 'Team'})

    joined = df.merge(toi, how='left', on=['_Secs', 'Game']).drop('_Secs', axis=1)

    return joined


def _opp_cols_to_back(df):
    """
    Extracts columns starting with "Opp" and moves them to the end.

    :param df: dataframe

    :return: dataframe with reordered columns
    """

    cols = list(df.columns)
    oppcols = {col for col in cols if len(col) >= 3 and col[:3] == 'Opp'}

    neworder = [x for x in df.columns if x not in oppcols] + [x for x in df.columns if x in oppcols]
    return df[[neworder]]


def _add_times_to_file(df, periodcol, timecol, time_format):
    """
    Uses specified periodcol, timecol, and time_format col to calculate _Secs, time elapsed in game.

    :param df: dataframe
    :param periodcol: str, the column that holds period name/number (1, 2, 3, 4 or OT, etc)
    :param timecol: str, the column that holds time in m:ss format
    :param time_format: use 'elapsed' (preferred) or 'remaining'. This refers to timecol: e.g. 120 secs elapsed in
    the 2nd period might be listed as 2:00 in timecol, or as 18:00.

    :return: dataframe with extra column _Secs, time elapsed in game.
    """

    df = df.dropna(subset={timecol})
    df.loc[:, periodcol] = df[periodcol].fillna(method='ffill')

    df.loc[:, '_MMSS'] = df[timecol].apply(lambda x: helpers.mmss_to_secs(x))

    if time_format == 'elapsed':
        def period_cont(x):
            y = str(x)[0]  # take just first since this may be a float
            if y.isdigit():
                return (x - 1) * 1200
            elif x == 'OT':  # OT
                return period_cont(4)
            else:
                print('Cannot find period contribution for', x)
                return ''

        df.loc[:, '_Period_Contribution'] = df[periodcol].apply(lambda x: period_cont(x))
        df.loc[:, '_Secs'] = df['_Period_Contribution'] + df['_MMSS']
        df.drop({'_MMSS','_Period_Contribution'}, axis=1, inplace=True)
    elif time_format == 'remaining':
        def period_cont(x):
            y = str(x)[0]  # take just first since this may be a float
            if y.isdigit():
                return x * 1200
            elif x == 'OT':
                return 3900
            else:
                print('Cannot find period contribution for', x)
                return ''

        df.loc[:, '_Period_Contribution'] = df[periodcol].apply(lambda x: period_cont(x))
        df.loc[:, '_Secs'] = df['_Period_Contribution'] - df['_MMSS']

    df.drop({'_MMSS','_Period_Contribution'}, axis=1, inplace=True, errors='ignore')
    return df



def _read_tracking_file(fname):
    """
    A method that will read csv or excel, depending on fname extension.

    :param fname: str, file path

    :return: dataframe in the file
    """

    if fname[-4:] == '.csv':
        return pd.read_csv(fname)
    elif fname[-5:] == '.xlsx':
        return pd.read_excel(fname)
    else:
        print('Did not recognize extension for', fname)