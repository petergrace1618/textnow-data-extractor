import argparse
import json
import pathlib
import re
import sys
from datetime import datetime, timezone, timedelta
from glob import glob
from sys import exit
from urllib import parse


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

    incident_calls = [c for c in call_data if d1 <= c['start_time'] <= d2]

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
    # TODO: fix when calls and/or messages is empty
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


def json2txt(obj):
    incoming, outgoing, me = 1, 2, '+15037564626'

    def format_metadata():
        obj_type_text = {
            'in':              'Incoming call',
            'out':             'Outgoing call',
            'text':            'Text message ',
            'voicemail-media': 'Voicemail    ',
            'media':           'Media message'
        }[obj_type]
        direction_text = {
            incoming: 'from ← ← ←',
            outgoing: 'to → → → →'
        }[direction]
        s = dt + eol
        s += f'{obj_type_text} {direction_text} {redacted(pn)} {get_contact_name(pn)}' + eol
        return s

    # obj is message
    if 'date' in obj:
        # phone number
        pn = normalize_number(obj['contact_value'])
        # datetime
        dt = iso2localf(obj['date'])
        direction = obj['direction']

        # get message type. message types are: text, voicemail, media
        url_regex = r'https://(voicemail-media|media)\.textnow\.com/?\?h=(.*)'
        url_match = re.match(url_regex, obj['message'])

        if url_match:
            obj_type = url_match.group(1)
            media_file = url_match.group(2)
        else:
            obj_type = 'text'
            media_file = None

        txt = format_metadata()

        if obj_type == 'text':
            txt += f'"{obj["message"]}"' + eol

        elif obj_type == 'voicemail-media':
            vm_path = pathlib.Path('textnow-data', 'voicemail', parse.unquote(media_file))
            print(vm_path)
            txt += f'[File: {vm_path}]' + eol

        elif obj_type == 'media':
            media_path = pathlib.Path('textnow-data', 'media')
            media_file_stem = media_file
            media_files = list(media_path.glob(f'{media_file_stem}*'))
            if len(media_files) > 1:
                raise ValueError(f'Duplicate media files {media_files}')
            print(media_files[0])
            txt += f'[File: {media_file[0]}]' + eol

        else:
            raise TypeError('Unknown message type')

    # obj is call
    elif 'start_time' in obj:
        caller = normalize_number(obj['caller'])
        called = normalize_number(obj['called'])
        dt = iso2localf(obj['start_time'])
        obj_type, direction, pn = {
            True: ('in', incoming, caller),
            False: ('out', outgoing, called)
        }[called == me]
        txt = format_metadata()
        txt += f"Duration {format_duration(obj['duration'])}" + eol

    # unknown object
    else:
        print(obj)
        raise TypeError('Unknown object type')

    txt += eol
    return txt

### BEGIN helper functions for json2html()
# local time zone abbreviations
tz = {
    'Pacific Daylight Time': 'PDT',
    'Pacific Standard Time': 'PST'
}

def iso2localf(iso):
    """Converts an ISO datetime string to a local datetime string
    in human-readable format. """

    # local datetime
    ldt = datetime.fromisoformat(iso).astimezone()

    # local datetime formatted
    # Format: Sat Nov 02 2024 01:30:53 AM
    ldtf = ldt.strftime('%a %b %d %Y %I:%M:%S %p')

    s = f'{ldtf} {tz[ ldt.tzname() ]}'
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
        epilog='''EXAMPLE: "%(prog)s -p 5032271212 -dd 2024-05-31 
        2024-05-01 -f may-radiocabs.txt" saves all calls/messages to/from 
        Radio Cab in May of 2024 to a file named may-radiocabs.txt.''')

    # TODO: create -c/--contacts option to print contacts
    #  Make mutually exclusive groups. -n | -c |  -p [ -d | -dd ] --html -f
    parser.add_argument('-f', '--file',
                        type=pathlib.Path,
                        default=default_output_file,
                        help='Save call & message data to FILE')
    parser.add_argument('-n', '--name',
                        action=PrintMatchingContactsAndExitAction,
                        metavar='PATTERN',
                        help='List all contacts matching %(metavar)s and exit')
    parser.add_argument('-c', '--contacts',
                        action=PrintContactsAndExitAction,
                        nargs=0,
                        help='Print all contacts and exit')
    parser.add_argument('-p', '--phone',
                        help='Phone # of contact to extract call/message data from')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d', '--date',
                        action=SetIntervalForSingleDateAction,
                        type=datetime.fromisoformat,
                        help='A single date to extract call/message data from')
    group.add_argument('-dd', '--dates',
                        action=ValidateAndNormalizeDateIntervalAction,
                        nargs=2, metavar='DATE',
                        type=datetime.fromisoformat,
                        help='A date interval to extract call/message data from')
    parser.add_argument('--html',
                        action='store_true', default=False,
                        help='Output as HTML. Default is plain text.')


    # command line arguments
    # cl = '-dd 2024-11-02 2024-11-05'.split()
    cl = '-dd 2024-11-02 2024-11-04 --html -f incident-calls-and-messages-log.html'.split()
    cl = '-c'.split()

    if len(cl) == 0:
        parser.print_usage()
        exit()

    args = parser.parse_args(cl)

    if args.dates is None:
        print_err('error', 'no dates specified', fatal=True)
    return args

# BEGIN helper classes for parse_args()

class PrintContactsAndExitAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, pattern, option_strings=None):
        global contacts
        contacts = get_contacts_from_user_shard()
        num = 0
        for (p, n) in contacts.items():
            print(f'"{n}", {p}')
            num += 1
        print(num, 'contacts')
        exit()


class PrintMatchingContactsAndExitAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, pattern, option_strings=None):
        global contacts
        contacts = get_contacts_from_user_shard()
        num = 0
        for (p, n) in contacts.items():
            if re.search(pattern, n, flags=re.IGNORECASE):
                print(n, p)
                num += 1
        if num == 0:
            print(f'No results for "{pattern}"')
        exit()


class ValidateAndNormalizeDateIntervalAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, ns, dates, option_strings=None):
        if dates[0] == dates[1]:
            print_err('error', ' dates can not be equal', fatal=True)

        # ensure args.date[0] < args.date[1]
        if dates[1] < dates[0]:
            dates[0], dates[1] = dates[1], dates[0]

        attrs = ['hour', 'minute', 'second', 'microsecond']
        if sum([getattr(dates[1], attr) for attr in attrs]) == 0:
            dates[1] = dates[1].replace(hour=23, minute=59, second=59, microsecond=999999)

        ns.dates = [dt.astimezone(tz=timezone.utc) for dt in dates]


class SetIntervalForSingleDateAction(argparse.Action):
    # calls.json
    # start: 2016-06-06T22:13:18.000+00:00
    # end: 2025-03-18T19:37:25.000+00:00
    # messages.json
    # start: 2016-03-14T23:13:34.000Z
    # end: 2025-03-19T04:30:09.000Z
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, ns, date, option_string=None):
        ns.dates = []
        ns.dates.append(date)
        beginning_of_day = date.replace(
            hour=0, minute=0, second=0, microsecond=0)
        one_day = timedelta(days=1, microseconds=-1)
        end_of_day = beginning_of_day + one_day
        ns.dates.append(end_of_day)

        # make datetimes aware in utc time
        ns.dates = [dt.astimezone(tz=timezone.utc) for dt in ns.dates]

# END helper classes for parse_args()


def print_err(level, msg, fatal=False):
    print(f'{pathlib.Path(sys.argv[0]).name}: {level}: {msg}',
        file=sys.stderr)
    if fatal:
        exit(1)


# GLOBALS ------
contacts = None
eol = '\n'
value_pattern = re.compile(r'\+?1?(\d{10})')
name_pattern = re.compile('[a-zA-Z]+$')
default_date_interval = [
    datetime.fromisoformat('2016-03-14T23:13:34.000Z'),
    datetime.fromisoformat('2025-03-19T04:30:09.000Z')]
default_output_file = 'textnow-data-extractor-output.txt'
# ---------------

if __name__ == '__main__':
    args = parse_args()

    if args.html and str(args.file) == default_output_file:
            args.file = args.file.with_suffix('.html')

    path = args.file

    contacts = get_contacts_from_user_shard()

    ante = args.dates[0].isoformat()
    post = args.dates[1].isoformat()
    calls_and_messages = merge_calls_messages(ante, post)

    # horizontal ruler
    hr = '-' * 52 + eol
    header = ''
    if args.html:
        header += '<!doctype html>\n<html>\n<head>\n'
        header += '<style> pre { font-family: monospace; } </style>\n'
        header += '</head>\n<body>\n<pre>\n'

    header += hr
    header += f'FILENAME: {path}' + eol
    header += f'DATE INTERVAL START: {iso2localf(ante)}' + eol
    header += f'DATE INTERVAL END  : {iso2localf(post)}' + eol
    header += f'CONTACT(S): '

    if args.phone:
        phone = normalize_number(args.phone)
        name = get_contact_name(phone)
        contact = f'{phone} {name}'
    else:
        contact = 'All'

    header += contact + eol
    header += hr + eol

    body = ''
    for o in calls_and_messages:
        body += json2txt(o)

    footer = hr
    if args.html:
        footer += '</pre>\n</body>\n</html>'

    doc = header + body + footer

    with path.open(encoding='utf-8', mode='w') as f:
        f.write(doc)

    print(f'Saved to "{path}"')