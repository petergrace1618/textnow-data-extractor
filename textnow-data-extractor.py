import argparse
import json
import pathlib
import re
import sys
from datetime import datetime, timezone, timedelta
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


def merge_calls_messages(d1, d2, pn):
    """
    :rtype: list
    """

    # load call data
    with open('textnow-data/calls.json', encoding='utf-8') as f:
        call_data = json.load(f)

    incident_calls = []
    for call in call_data:
        if d1 <= call['start_time'] <= d2:
            if pn is None:
                incident_calls.append(call)
            elif pn == call['caller'] or pn == call['called']:
                incident_calls.append(call)

    # load message data
    with open('textnow-data/messages.json', encoding="utf-8") as f:
        message_data = json.load(f)

    incident_messages = []
    for message in message_data:
        if d1 <= message['date'] <= d2:
            if pn is None:
                incident_messages.append(message)
            elif pn == message['contact_value']:
                incident_messages.append(message)

    # the data in each file is already sorted by date
    # so just have to merge them together based on date
    return merge_longest(incident_calls, incident_messages)


### BEGIN Helper function for merge_calls_messages()
def merge_longest(calls, messages):
    """An ad hoc version of itertools.zip_longest.
    Instead of returning a list of tuples, it returns
    the two lists merged in chronological order."""
    if len(calls) == 0 or len(messages) == 0:
        return calls + messages
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

    # message object
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

        # TEXT MESSAGE
        if obj_type == 'text':
            txt += f'"{obj["message"]}"' + eol

        # VOICEMAIL MESSAGE
        elif obj_type == 'voicemail-media':
            vm_path = pathlib.Path('textnow-data', 'voicemail', parse.unquote(media_file))
            print(obj['date'], vm_path, sep='\n')
            if args.html:
                txt += f'<audio controls src="{vm_path}"></audio>' + eol
            else:
                txt += f'[File: {vm_path}]' + eol

        # MEDIA MESSAGE
        elif obj_type == 'media':
            media_path = pathlib.Path('textnow-data', 'media')
            media_file_stem = media_file
            media_files = list(media_path.glob(f'{media_file_stem}*'))
            if len(media_files) > 1:
                raise ValueError(f'Duplicate media files {media_files}')
            print(obj['date'], media_files[0], sep='\n')
            if args.html:
                txt += f'<img src="{media_files[0]}" alt="{media_files[0]}">' + eol
            else:
                txt += f'[File: {media_files[0]}]' + eol

        else:
            raise TypeError('Unknown message type')

    # call object
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
        and are converted to local time. If no file is specified, saves
        output to textnow-data-extractor-output.txt''',
        epilog='''EXAMPLE: "$%(prog)s -p 5032271212 -dd 2024-05-31 
        2024-05-01 -f may-radiocabs.txt" saves all calls/messages to/from 
        Radio Cab in May of 2024 to a file named may-radiocabs.txt.''')

    # TODO: Make mutually exclusive groups.
    #  [ -n | -c | -t | -p ] [ -d | -dd ] [ --html | --json ] [ -f ]
    top_level_group = parser.add_mutually_exclusive_group()
    top_level_group.add_argument('-c', '--contacts',
                        action=PrintContactsAndExitAction,
                        nargs=0,
                        help='Print all contacts and exit')
    top_level_group.add_argument('-t', '--timespan',
                        action=PrintDatetimeLimitsAndExit,
                        nargs=0,
                        help='Print the earliest and latest datetimes in calls.json and messages.json and exit')
    top_level_group.add_argument('-n', '--name',
                        action=PrintMatchingContactsAndExitAction,
                        metavar='PATTERN',
                        help='List all contacts matching %(metavar)s and exit')
    top_level_group.add_argument('-p', '--phone',
                        action=ValidatePhoneNumberAction,
                        help='Phone # of contact to extract call/message data from',)
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('-d', '--date',
                        action=SetIntervalForSingleDateAction,
                        type=datetime.fromisoformat,
                        help='A single date to extract call/message data from')
    date_group.add_argument('-dd', '--dates',
                        action=ValidateAndNormalizeDateIntervalAction,
                        nargs=2, metavar='DATE',
                        type=datetime.fromisoformat,
                        help='A date interval to extract call/message data from')
    file_type_group = parser.add_mutually_exclusive_group()
    file_type_group.add_argument('--html',
                        action='store_true', default=False,
                        help='Output as HTML.')
    file_type_group.add_argument('--raw',
                         action='store_true', default=False,
                         help='Output as JSON.')
    parser.add_argument('-f', '--file',
                        type=pathlib.Path,
                        default=default_output_file,
                        help='Save call & message data to FILE')

    # command line arguments
    # cl = '-h'
    # cl = ''
    # cl = '-d 2024-11-01 -p 5033449503 -f Pre-Incident-Calls-and-Messages.txt'
    # cl = '-dd 2024-11-02 2024-11-04 -f Incident-Calls-and-Messages.html --html'
    # cl = '-dd 2024-11-02 2024-11-04 -f Incident-Calls-and-Messages.txt'
    cl = '-d 2024-11-02  --raw'
    # cl = '-n gyps'

    cl = cl.split()

    if len(cl) == 0:
        parser.print_usage()
        exit(1)

    args = parser.parse_args(cl)

    if args.dates is None:
        print('No dates specified')
        parser.print_usage()
        exit(1)

    return args

# BEGIN helper classes for parse_args()

class ValidatePhoneNumberAction(argparse.Action):
    def __call__(self, parser, ns, phone_number, option_string=None):
        global contacts
        contacts = get_contacts_from_user_shard()
        phone_number = normalize_number(phone_number)
        if phone_number not in contacts:
            exit(f'No results for {phone_number}')
        ns.phone = phone_number


class PrintDatetimeLimitsAndExit(argparse.Action):
    def __call__(self, parser, namespace, values, option_strings=None):
        d = {}
        # load call data
        with open('textnow-data/calls.json', encoding='utf-8') as f:
            call_data = json.load(f)
        d[self.fdt(call_data[0]['start_time'])] = 'calls.json'
        d[self.fdt(call_data[-1:][0]['start_time'])] = 'calls.json'
        del call_data

        # load message data
        with open('textnow-data/messages.json', encoding="utf-8") as f:
            message_data = json.load(f)

        d[self.fdt(message_data[0]['date'])] = 'messages.json'
        d[self.fdt(message_data[-1:][0]['date'])] = 'messages.json'

        for dt in sorted(d.keys()):
            print(dt, d[dt])

        exit()

    # create local datetime from utc iso, make naive, and return iso string
    def fdt(self, iso):
        return datetime.isoformat(
            datetime.fromisoformat(iso).astimezone().replace(tzinfo=None))


class PrintContactsAndExitAction(argparse.Action):
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

        # if no time specified on end date, make it end of day
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
        length_of_one_day = timedelta(days=1, microseconds=-1)
        end_of_day = beginning_of_day + length_of_one_day
        ns.dates.append(end_of_day)

        # make datetimes aware in utc time
        ns.dates = [dt.astimezone(tz=timezone.utc) for dt in ns.dates]

# END helper classes for parse_args()


def print_err(level, msg, fatal=False):
    print(f'{pathlib.Path(sys.argv[0]).name}: {level}: {msg}',
        file=sys.stderr)
    if fatal:
        exit(1)


def format_header():
    h = ''
    if args.html:
        h += '<!doctype html>\n<html>\n<head>\n'
        h += '<style>\n'
        h += 'pre { font-family: Roboto, monospace;'
        h += '  font-size: 1.2em;'
        h += '  width: 100%;'
        h += '  text-wrap: wrap;'
        h += '}\n'
        h += 'img { max-width: 600px; '
        h += '  border: 1px black solid;'
        h += '  border-radius: 1rem;'
        h += '}\n'
        h += '</style>\n</head>\n<body>\n<pre>\n'

    h += hr
    h += f'FILENAME   : {path}\n'
    h += f'START DATE : {iso2localf(ante)}\n'
    h += f'END DATE   : {iso2localf(post)}\n'
    h += f'CONTACT(S) : '

    if args.phone:
        contact = f'{args.phone} {get_contact_name(args.phone)}'
    else:
        contact = 'All'

    h += contact + '\n'
    h += '\n'
    h += '(For source code see:\n'
    if args.html:
        h += '<a href="https://github.com/petergrace1618/textnow-data-extractor.git">'

    h += 'https://github.com/petergrace1618/textnow-data-extractor.git'

    if args.html:
        h += '</a>'
    h += ')\n'
    h += hr + '\n'
    return h


# GLOBALS ------
contacts = None
eol = '\n'
hr = '-' * 60 + eol     # horizontal ruler
value_pattern = re.compile(r'\+?1?(\d{10})')
name_pattern = re.compile('[a-zA-Z]+$')
default_date_interval = [
    datetime.fromisoformat('2016-03-14T23:13:34.000Z'),
    datetime.fromisoformat('2025-03-19T04:30:09.000Z')]
default_output_file = 'textnow-data-extractor-output.txt'
# ---------------

if __name__ == '__main__':
    args = parse_args()
    # print(args)

    # if --html/--json option specified, change file extension
    if str(args.file) == default_output_file:
        if args.html:
            args.file = args.file.with_suffix('.html')
        elif args.raw:
            args.file = args.file.with_suffix('.raw.txt')

    path = args.file

    if contacts is None:
        contacts = get_contacts_from_user_shard()

    # ante facto, post facto
    ante = args.dates[0].isoformat()
    post = args.dates[1].isoformat()
    calls_and_messages = merge_calls_messages(ante, post, args.phone)

    if len(calls_and_messages) == 0:
        exit(f'No results for {args.phone} between {ante} and {post}')

    header = format_header()

    body = ''
    for obj in calls_and_messages:
        if args.raw:
            body += json.dumps(obj, ensure_ascii=False, indent=4) + ',\n'
        else:
            body += json2txt(obj)

    footer = hr
    footer += f'END: {path}\n'
    if args.html:
        footer += '</pre>\n</body>\n</html>'

    doc = header + body + footer

    with path.open(encoding='utf-8', mode='w') as f:
        f.write(doc)

    print(f'Saved to "{path}"')
