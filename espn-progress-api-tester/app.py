import datetime
import json

import requests


def tester(event=None, context=None):
    today = datetime.datetime.today() - datetime.timedelta(hours=8)
    today_string = today.strftime("%Y%m%d")
    nfl_game_status_endpoint = (
        f'https://site.api.espn.com/apis/fantasy/v2/games/ffl/games?'
        f'useMap=true&dates={today_string}&pbpOnly=true'
    )
    headers = {'Cache-Control': 'no-cache'}
    r = requests.get(nfl_game_status_endpoint, headers=headers)
    nfl_games = r.json()['events']
    game_progress = {}
    for event in nfl_games:
        minutes_left = int(60 - round((event['percentComplete'] / 100) * 60, 0))
        teams = []
        for team in event['competitors']:
            teams.append(team['abbreviation'])
        game_progress['/'.join(teams)] = minutes_left

    groupme_endpoint = 'https://api.groupme.com/v3/bots/post'
    test_bot_id = 'a4d8006d29f3bf75d1e206c88f'
    message = '\n'.join([f'{teams}:  {mins}' for teams, mins in game_progress.items()])
    data = {'bot_id': test_bot_id, 'text': f'old\n\n{message}'}
    requests.post(groupme_endpoint, data=data)


if __name__ == '__main__':
    tester()
