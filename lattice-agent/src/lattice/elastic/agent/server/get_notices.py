import datetime
import json
import requests  # type: ignore
import socket

already_preempted = False


def get_auth_token(ttl):
    get_token_header = {
        "X-aws-ec2-metadata-token-ttl-seconds": str(ttl)
    }
    response = requests.put("http://169.254.169.254/latest/api/token", headers=get_token_header)

    token = b''
    if response.status_code == 200:
        token = response.content
    else:
        print('Getting token failed with code {}'.format(response.status_code))

    return token


def check_for_preemption(breeze_store):
    # Assume that if this if failing we are not running in AWS
    try:
        token = get_auth_token(21600)
    except requests.exceptions.ConnectionError:
        return

    get_action_header = {
        "X-aws-ec2-metadata-token": token,
    }
    response = requests.get('http://169.254.169.254/latest/meta-data/spot/instance-action', headers=get_action_header)

    http_code = response.status_code

    global already_preempted
    if http_code == 401:
        token = get_auth_token(30)
    elif http_code == 200 and not already_preempted:
        # TODO (JOHN): Need to make sure this is thread safe in case
        # multiple preemptions occur simultaneously. Fine for now
        preemptions_so_far = json.loads(breeze_store.compare_set('preemptions', '', '[]'))
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        hostname = socket.gethostbyname(socket.gethostname())
        preemptions_so_far.append((timestamp, hostname))
        breeze_store.set('preemptions', json.dumps(preemptions_so_far))
        already_preempted = True
    else:
        pass
