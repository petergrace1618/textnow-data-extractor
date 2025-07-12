import argparse
import json
import re
import os
import pathlib
from sys import exit
from datetime import datetime
from urllib import parse
from glob import glob


def get_contacts_from_user_shard():
    """Returns a dict in the form
    {'+1##########': 'name', ...}"""
    contacts = {}

    with open('textnow-data/user_shard.json', 'r', encoding='utf-8') as f:
        user_shard = json.load(f)
    user_shard_contacts = user_shard['contacts']
    del user_shard

    for contact in user_shard_contacts:
        name = contact['name']
        phone_number = normalize_number(contact['contact_value'])

        if not (isvalid_name(name) and phone_number):
            continue

        if phone_number in contacts:
            if name != contacts[phone_number]:
                raise ValueError(f'Name conflict: "{phone_number}": "{contacts[phone_number]}" and "{name}"')
        else:
            # create new item -> 'value': ['name']
            contacts[phone_number] = name

    contacts['Restricted'] = ''
    contacts['+2999999999'] = ''
    return contacts

### BEGIN helper function for get_contacts_from_user_shard()
def isvalid_name(n):
    return name_pattern.search(n)
### END helper function for get_contacts_from_user_shard()


def merge_calls_messages(d1, d2):
    """
    :rtype: list
    """
    # # Nov 2 2024 12:00 AM PDT
    # d1 = '2024-11-02T08:00'
    # # Nov 4 2024 11:59 PM PST
    # d2 = '2024-11-05T07:59'

    # load call data
    with open('textnow-data/calls.json', encoding='utf-8') as f:
        call_data = json.load(f)

    # load message data
    with open('textnow-data/messages.json', encoding="utf-8") as f:
        message_data = json.load(f)

    #TODO: convert utc times to local

    # extract call data from the time surrounding the incident
    incident_calls = [c for c in call_data if d1 <= c['start_time'] <= d2]

    # extract message data from the time surrounding the incident
    incident_messages = [m for m in message_data if d1 <= m['date'] <= d2]

    # the data in each file is already sorted by date
    # so just have to merge it together based on date
    return merge_longest(incident_calls, incident_messages)


### BEGIN Helper function for merge_calls_messages()
def merge_longest(calls, messages):
    """An ad hoc version of itertools.zip_longest.
    Instead of returning a list of tuples, it returns
    the two lists merged in chronological order.
    53 elements in incident-calls.json
    112 elements in incident-messages.json"""
    merged = []
    c = iter(calls)
    m = iter(messages)
    call = next(c)
    message = next(m)
    while True:
        if datetime_key(call) < datetime_key(message):
            merged.append(call)
            try:
                call = next(c)
            except StopIteration:
                # append the rest of messages onto merged
                fill = m
                break
        else:
            merged.append(message)
            try:
                message = next(m)
            except StopIteration:
                # append the rest of calls onto merged
                fill = c
                break
    for o in fill:
        merged.append(o)
    return merged

### BEGIN Helper function for merge_longest()
def datetime_key(o):
    if 'start_time' in o:
        return o['start_time']
    if 'date' in o:
        return o['date']
    raise TypeError
### END Helper function for merge_longest()
### END Helper functions for merge_calls_messages()


def json2html(obj):
    incoming, outgoing, me = 1, 2, '+15037564626'

    def format_metadata():
        obj_type_text = {
            'in': 'Incoming call',
            'out': 'Outgoing call',
            'text': 'Text message&nbsp;',
            'voicemail-media': 'Voicemail&nbsp;&nbsp;&nbsp;&nbsp;',
            'media': 'Media message'
        }[obj_type]
        direction_text = {
            incoming: 'from',
            outgoing: 'to &nbsp;'
        }[direction]
        s = dt + eol
        s += f'{obj_type_text} {direction_text} {redacted(pn)} {get_contact_name(pn)}' + eol
        return s

    # obj is message
    if 'date' in obj:
        # phone number
        pn = normalize_number(obj['contact_value'])
        # datetime
        dt = iso2local(obj['date'])
        direction = obj['direction']

        # get message type. message types are: text, voicemail, media
        url_regex = r'https://(voicemail-media|media)\.textnow\.com/?\?h=(.*)'
        url_match = re.match(url_regex, obj['message'])
        if url_match:
            obj_type = url_match.group(1)
            media_file = url_match.group(2)
        else:
            obj_type = 'text'

        html = format_metadata()

        if obj_type == 'text':
            html += f'"{obj["message"]}"' + eol

        elif obj_type == 'voicemail-media':
            vm_path = 'textnow-data/voicemail/' + parse.unquote(media_file)
            print(vm_path)
            html += f'File: {vm_path}' + eol

        elif obj_type == 'media':
            media_path = f'textnow-data/media/{media_file}*'
            files = glob(media_path)
            if len(files) > 1:
                raise ValueError('Duplicate media files')
            html += f'File: {files[0]}' + eol
            print(files[0])

        else:
            raise TypeError('Unknown message type')

    # obj is call
    elif 'start_time' in obj:
        caller = normalize_number(obj['caller'])
        called = normalize_number(obj['called'])
        dt = iso2local(obj['start_time'])
        obj_type, direction, pn = {
            True: ('in', incoming, caller),
            False: ('out', outgoing, called)
        }[called == me]
        html = format_metadata()
        html += f"Duration {format_duration(obj['duration'])}" + eol

    # unknown object
    else:
        print(obj)
        raise TypeError('Unknown object type')

    html += '<br>\n'
    return html

### BEGIN helper functions for json2html()
# local time zone abbreviations
tz = {
    'Pacific Daylight Time': 'PDT',
    'Pacific Standard Time': 'PST'
}

def iso2local(iso):
    """Converts an ISO format datetime string
    to one in local timezone. """
    # local datetime
    ldt = datetime.fromisoformat(iso).astimezone()

    # local datetime formatted
    # Format: Sat Nov 02 2024 01:30:53 AM
    ldtf = ldt.strftime('%a %b %d %Y %I:%M:%S %p')

    s = f'{ldtf} {tz[ldt.tzname()]}'
    return s

def get_contact_name(num):
    # try:
    c = contacts.get(normalize_number(num), '')
    # except KeyError:
    #     c = ''
    return c

def format_duration(d):
    m, s = divmod(d, 60)
    return f"{d} ({int(m)}m {int(s)}s)"

def redacted(pn):
    """Replace the last four digits of the phone number with X's.
    """
    if pn == 'Restricted':
        return pn
    return pn[0:8] + 'XXXX'
### END helper functions for json2html()

### BEGIN helper function for get_contact_name(),
### get_contact_from_user_shard(), and json2html()
def normalize_number(v):
    """If v is of the form /\\+?1?\\d{10}/
    then v is normalized to /\\+1\\d{10}/,
    else None is returned."""
    # if no match v will be 'Restricted' or 'Unknown number'
    m = value_pattern.fullmatch(v)
    return f'+1{m.group(1)}' if m else v
### END helper function for get_contact_name(),
### get_contact_from_user_shard(), and json2html()


def parse_args():
    parser = argparse.ArgumentParser(
        description=''' Merges call and message data chronologically 
        from textnow-data/calls.json and textnow-data/messages.json 
        using contacts from textnow-data/user_shard.json. Call/message 
        data are then extracted for the given contact in the given time 
        span. If -n/--name option is specified, all phone number(s) 
        matching NAME are printed before exiting; all other options are 
        ignored. If only -p/--phone option is specified, all call/message 
        data for the given phone # is extracted. If only -d/--date 
        option is specified, call/message data is extracted for all 
        contacts in the given timespan. Dates must be in ISO format, 
        and are converted to local time.''',
        epilog=''' EXAMPLE: "%(prog)s -p 5032271212 -d 2024-05-31 -d 
        2024-05-01 may-radiocabs.txt" saves all calls/messages to/from 
        Radio Cab in May of 2024 to a file named may-radiocabs.txt.''')

    parser.add_argument('file',
                        nargs=1, type=pathlib.Path,
                        help='Save call/message data to FILE')
    parser.add_argument('-n', '--name',
                        metavar='PATTERN',
                        help='List all contacts matching %(metavar)s and exit')
    parser.add_argument('-p', '--phone',
                        help='Phone # of contact to extract call/message data from')
    parser.add_argument('-d', '--date',
                        action='append', metavar='DATE',
                        type=datetime.fromisoformat,
                        help='Date(s) of timespan of call/message data to extract')

    cl = '-d 2023-03-07t12:00 -d 2023-03-08 incident.html'
    ns = parser.parse_args(cl.split())
    normalize_date_interval(ns)
    return ns


def normalize_date_interval(ns):
    #TODO: make datetimes aware

    pass


def print_matching_contacts_and_exit(name: str) -> None:
    num = 0
    for (p, n) in contacts.items():
        if re.search(name, n, flags=re.IGNORECASE):
            print(n, p)
            num += 1
    if num == 0:
        print(f'No results for "{name}"')
    exit()


if __name__ == '__main__':
    eol = '<br>\n'
    # used by normalize_number and isvalid_name
    value_pattern = re.compile(r'\+?1?(\d{10})')
    name_pattern = re.compile('[a-zA-Z]+$')

    args = parse_args()

    path = args.file[0]
    if path.exists():
        ok = input(f'File "{path}" already exists. Overwrite? ') + '\n'
        if ok[0] not in ['y', 'Y']:
            print(f'Writing to "{path}" aborted')
            exit()

    contacts = get_contacts_from_user_shard()

    if args.name:
        print_matching_contacts_and_exit(args.name)

    [ante, post] = ['2024-11-02', '2024-11-05']
    calls_and_messages = merge_calls_messages(ante, post)

    header = '<!doctype html>\n<html>\n<head>\n'
    header += '   <style> body { font-family: monospace; } </style>\n'
    header += '</head>\n<body>\n'

    body = 'CALL AND MESSAGE DATA EXTRACTED FROM TEXTNOW DATA DISCLOSURE PACKAGE' + eol
    body += eol
    body += f'FILENAME: {path}' + eol
    body += f'DATES: {ante} to {post}' + eol
    body += f'CONTACT(S): '

    if args.phone:
        phone = normalize_number(args.phone)
        name = get_contact_name(phone)
        contact = f'{phone} {name}'
    else:
        contact = 'All'

    body += contact + eol
    body += '-' * 50 + eol + eol
    # print(body)
    # exit()

    for o in calls_and_messages:
        body += json2html(o)

    footer = '''</body>\n</html>'''
    doc = header + body + footer

    with path.open(encoding='utf-8', mode='w') as f:
        f.write(doc)
