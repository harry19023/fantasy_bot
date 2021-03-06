import datetime
from time import time
import os

import boto3
from dateutil import tz
import matplotlib.pyplot as plt
import requests

from espn_api.football import League

db = boto3.client('dynamodb')
tablename = 'ff-espn-bot-LeagueTable-1LNQVCZV3UU3M'
espn_username = 'harry19023@gmail.com'
espn_password = 'ETOkoF0YdWY4a'
groupme_endpoint = 'https://api.groupme.com/v3/bots/post'
access_token = "0J1aBgnLyfSBgP7XHrHbw1op2qOG7DTvG9Jsfw7Z"
test_bot_id = 'a4d8006d29f3bf75d1e206c88f'


def make_matplotlib_table(data, cols, colors, filename):
    fig, ax = plt.subplots()
    fig.patch.set_visible(False)  # Hide axes
    ax.axis('off')
    ax.axis('tight')
    table = ax.table(cellText=data, cellColours=colors, colLabels=cols, loc='center')
    ax.margins(0)
    table.auto_set_font_size(False)
    table.set_fontsize(14)
    table.auto_set_column_width([0, 1, 2, 3])

    if len(data[0]) > 3:  # only for the points table, not standings
        cellDict = table.get_celld()
        big_rows = {}
        for i, row in enumerate(data):
            if row[3].count(',') > 0:
                big_rows[i] = row[3].count(',') + 1
        for row in big_rows:
            for i in range(4):
                cellDict[(row + 1, i)].set_height((big_rows[row] / (len(data) + 1)) * .75)

    plt.gcf().set_size_inches(7.5, 6)
    filename = '/tmp/{}'.format(os.path.basename(filename))
    plt.gcf().savefig(filename, transparent=False)


def post_pic_to_groupme(filename, message, bot_id):
    filename = '/tmp/{}'.format(os.path.basename(filename))
    pic = open('{}.png'.format(filename), 'rb').read()
    headers = {'X-Access-Token': access_token, 'Content-Type': 'image/png'}
    r = requests.post('https://image.groupme.com/pictures', data=pic, headers=headers)
    pic_url = r.json()['payload']['url']
    data = {'bot_id': bot_id, 'text': message, 'picture_url': pic_url}
    r = requests.post(groupme_endpoint, data=data)


def scramble_handler(event, context):
    # decide if we should do projected (sunday early and late games) or actual
    # points (SNF, monday, tuesday games)
    from_zone = tz.gettz('UTC')
    to_zone = tz.gettz('America/Los_Angeles')
    current_time = datetime.datetime.today()
    current_time = current_time.replace(tzinfo=from_zone)
    current_time = current_time.astimezone(to_zone)
    if current_time.isoweekday() in [1, 2]:  # Monday or Tuesday
        actual_points = True
    elif current_time.isoweekday() != 0:  # Wed, Thurs, Fri, Sat
        actual_points = False
    elif current_time.hour < 17:  # Sunday before 5 PM PST
        actual_points = False
    else:  # Sunday after 5 PM PST
        actual_points = True
    current_time = current_time.strftime('%I:%M %p')
    print(current_time)
    if 'test' in event:
        test_scramble(False, actual_points)
        return
    results = db.scan(TableName=tablename, Select='ALL_ATTRIBUTES')['Items']

    leagues = {}
    for result in results:
        if 'scramble' in result:  # leagues with no scramble don't have the attribute
            league_id = result['league_id']['N']
            bot_id = result['bot_id']['S']
            scramble_weeks = [int(x) for x in result['scramble']['S'].split(',')]
            wildcard = bool(result['wildcard']['BOOL'])
            playoff_teams = int(result['playoff_teams']['N'])

            leagues[league_id] = {'bot_id': bot_id,
                                  'scramble_weeks': scramble_weeks,
                                  'wildcard': wildcard,
                                  'playoff_teams': playoff_teams}

    scramble_update(leagues, actual_points=actual_points)


def scramble_update(leagues, actual_points=False):
    current_week = None
    for league_id, league_data in leagues.items():
        print('Scramble for {}'.format(league_id))
        league = None
        if current_week is None:
            league = League(league_id, 2020, espn_username, espn_password)
            current_week = league.current_week  # only need to check this once, can skip leagues where not scramble
        if current_week not in league_data['scramble_weeks']:
            continue
        if league is None:
            league = League(league_id, 2020, espn_username, espn_password)  # only 1st league will have been init'd

        bot_id = league_data['bot_id']
        # bot_id = test_bot_id
        playoff_teams = league_data['playoff_teams']
        wildcard = league_data['wildcard']

        # If actual points, use box_score
        if actual_points:
            box_scores = league.box_scores()
            teams = []
            for box_score in box_scores:
                # prep home team
                box_score.home_team.actual = box_score.home_score
                box_score.home_team.players_remaining = []
                for player in box_score.home_lineup:
                    if (player.game_played == 0 and
                            player.slot_position not in ['BE', 'IR']):
                        box_score.home_team.players_remaining.append(player)
                teams.append(box_score.home_team)

                # prep away team
                box_score.away_team.actual = box_score.away_score
                box_score.away_team.players_remaining = []
                for player in box_score.away_lineup:
                    if (player.game_played == 0 and
                            player.slot_position not in ['BE', 'IR']):
                        box_score.away_team.players_remaining.append(player)
                teams.append(box_score.away_team)

            # sort teams by actual score and make scramble table
            teams = sorted(teams, key=lambda x: x.actual, reverse=True)

            cols = ['Team', 'Actual Points', 'Diff', 'Players Remaining']
            lowest_winning_score = teams[int((len(teams) / 2) - 1)].actual
            highest_losing_score = teams[int(len(teams) / 2)].actual
            data = []
            for i, team in enumerate(teams):
                row = []
                row.append(team.team_name)
                row.append(round(team.actual, 1))
                if i < len(teams) / 2:
                    row.append(round(team.actual - highest_losing_score, 1))
                else:
                    row.append(round(team.actual - lowest_winning_score, 1))
                row.append(',\n'.join(x.name for x in team.players_remaining))
                data.append(row)

        else:
            # else, use matchups, as it has better projected points functionality
            matchups = league.scoreboard()
            teams = []
            for matchup in matchups:
                matchup.home_team.projected = matchup.home_score_projected
                matchup.home_team.minutes_remaining = matchup.home_minutes_remaining
                teams.append(matchup.home_team)
                matchup.away_team.projected = matchup.away_score_projected
                matchup.away_team.minutes_remaining = matchup.away_minutes_remaining
                teams.append(matchup.away_team)

            # sort teams by projected score and make scramble table
            teams = sorted(teams, key=lambda x: x.projected, reverse=True)

            cols = ['Team', 'Proj Points', 'Mins Remaining', 'Diff']
            lowest_winning_score = teams[int((len(teams) / 2) - 1)].projected
            highest_losing_score = teams[int(len(teams) / 2)].projected
            data = []
            for i, team in enumerate(teams):
                row = []
                row.append(team.team_name)
                row.append(round(team.projected, 1))
                row.append(team.minutes_remaining)
                if i < len(teams) / 2:
                    row.append(round(team.projected - highest_losing_score, 1))
                else:
                    row.append(round(team.projected - lowest_winning_score, 1))
                data.append(row)
        # Make matplotlib table
        green_colors = [(0.0, 1.0, 0.0) for x in range(4)]
        colors = [green_colors for x in range(int(len(teams) / 2))]
        red_colors = [(1.0, 0.0, 0.0) for x in range(4)]
        colors.extend([red_colors for x in range(int(len(teams) / 2))])

        filename = f'scramble_{int(time())}'
        make_matplotlib_table(data, cols, colors, filename)

        # post to groupme
        from_zone = tz.gettz('UTC')
        to_zone = tz.gettz('America/Los_Angeles')
        current_time = datetime.datetime.today()
        current_time = current_time.replace(tzinfo=from_zone)
        current_time = current_time.astimezone(to_zone)
        current_time = current_time.strftime('%I:%M %p')

        message = 'Scramble as of {} PST'.format(current_time)
        post_pic_to_groupme(filename, message, bot_id)

        # calculate standings
        for i, team in enumerate(teams):
            if i < int(len(teams) / 2):
                team.wins += 1
            else:
                team.losses += 1
            if actual_points:
                team.points_for += team.actual
            else:
                team.points_for += team.projected
        teams = sorted(teams, key=lambda x: x.points_for, reverse=True)
        teams = sorted(teams, key=lambda x: x.wins, reverse=True)
        # find wildcard team
        non_playoffs = teams[int((len(teams) / 2) - 1):]
        non_playoffs = sorted(non_playoffs, key=lambda x: x.points_for, reverse=True)
        wildcard_team = non_playoffs[0].team_id

        # make matplotlib table
        cols = ['Team', 'Wins', 'Points For']
        data = []
        colors = []
        for i, team in enumerate(teams):
            row = []
            row.append(team.team_name)
            row.append(team.wins)
            row.append(round(team.points_for, 1))
            data.append(row)
            if wildcard:
                if i < playoff_teams - 1:
                    colors.append([(0.0, 1.0, 0.0) for x in range(3)])
                else:
                    if team.team_id == wildcard_team:
                        colors.append([(0.0, 1.0, 0.0) for x in range(3)])
                    else:
                        colors.append([(1.0, 0.0, 0.0) for x in range(3)])
            else:
                if i < playoff_teams:
                    colors.append([(0.0, 1.0, 0.0) for x in range(3)])
                else:
                    colors.append([(1.0, 0.0, 0.0) for x in range(3)])

        make_matplotlib_table(data, cols, colors, 'standings')

        # post to groupme
        message = 'Playoffs as of {} PST'.format(current_time)
        post_pic_to_groupme('standings', message, bot_id)


def test_scramble(real=False, actual_points=False):
    if real:
        leagues = {777493: {'bot_id': 'f0d5e4b7e448b15b5a851172c7',
                            'scramble_weeks': [12],
                            'wildcard': True,
                            'playoff_teams': 6},  # DHFFL
                   932584: {'bot_id': 'd1b3fe1d481235ff4f4b85067c',
                            'scramble_weeks': [4, 8, 12],
                            'wildcard': False,
                            'playoff_teams': 4},  # STL
                   1846399: {'bot_id': '4ef2106e348bed49ccac19f2eb',
                             'scramble_weeks': [12],
                             'wildcard': False,
                             'playoff_teams': 6}  # BSB
                   }
    else:
        leagues = {777493: {'bot_id': test_bot_id,
                            'scramble_weeks': [13],
                            'wildcard': True,
                            'playoff_teams': 6},  # DHFFL
                   932584: {'bot_id': test_bot_id,
                            'scramble_weeks': [4, 8, 12, 13],
                            'wildcard': False,
                            'playoff_teams': 4},  # STL
                   }
    scramble_update(leagues, actual_points)


if __name__ == '__main__':
    test_scramble(False, True)
