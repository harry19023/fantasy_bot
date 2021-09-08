import requests
import boto3
from espn_api.football import League

db = boto3.client('dynamodb')
tablename = 'ff-espn-bot-LeagueTable-1LNQVCZV3UU3M'
espn_username = 'harry19023@gmail.com'
espn_password = 'ETOkoF0YdWY4a'
groupme_endpoint = 'https://api.groupme.com/v3/bots/post'

def waiver_check(event, context):
    # leagues = {1414578: 'e0d734b87ec92d3d8af6ec965d',  # Kober
    #            777493: 'f0d5e4b7e448b15b5a851172c7',  # DHFFL
    #            932584: 'd1b3fe1d481235ff4f4b85067c',  # Wheaton
    #            1846399: '4ef2106e348bed49ccac19f2eb'  # BSB
    #            }

    results = db.scan(TableName=tablename, Select='ALL_ATTRIBUTES')['Items']
    leagues = {}
    for result in results:
        league_id = result['league_id']['N']
        bot_id = result['bot_id']['S']
        last_report_time = result['last_report_time']['S']
        leagues[league_id] = {'bot_id': bot_id, 'last_report_time': last_report_time}

    for league_id, league_data in leagues.items():
        bot_id = league_data['bot_id']
        last_report_time = league_data['last_report_time']
        year = 2021
        league = League(league_id, year, espn_username, espn_password)

        reports = league.free_agent_auction_report()
        if reports == 'There were no free agent auctions this week':
            print('No free agent auctions for {}'.format(league_id))
            continue

        time, report = reports[-1]
        if str(time) == last_report_time:
            print('Same report as last time. League: {} Time: {}'.format(league_id, time))
            continue

        messages = []
        message = f'Free Agent Report for {time.strftime("%a, %b %d")}\n\n'
        message_chunk = ''
        for line in report.split('\n'):
            if line == '':
                message_chunk += '\n\n'
                message += message_chunk
                message_chunk = ''
                continue
            if len(line) + len(message_chunk) + len(message) <= 1000:
                message_chunk += line + '\n'
            else:
                messages.append(message)
                message = message_chunk + line + '\n'
                message_chunk = ''
        if message_chunk != '':
            message += message_chunk
        messages.append(message)

        responses = []
        for message in messages:
            data = {'bot_id': bot_id, 'text': message}
            responses.append(requests.post(groupme_endpoint, data=data))

        update_expression = 'SET last_report_time = :l'
        expression_attribute_values = {':l': {'S': str(time)}}
        db.update_item(TableName=tablename,
                       Key={'league_id': {'N': league_id}},
                       UpdateExpression=update_expression,
                       ExpressionAttributeValues=expression_attribute_values,
                       ReturnConsumedCapacity='NONE')

        print('Posted new report. League: {}  Time: {}'.format(league_id, time))
    return
