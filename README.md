# tde -- TextNow Data Extractor
`tde` is a Python script which extracts the call and text message history from a TextNow data disclosure package, and outputs it in human-readable format. The necessity for the script is explained in [the project wiki](https://github.com/petergrace1618/textnow-data-extractor/wiki).

The data disclosure package is in the form of a ZIP file which has not been included in the repository because it contains personal information such as names, phone numbers, voicemails, and private text and media messages. 

The main functionality is performed by `merge_calls_messages()` and `json2txt()`. The former is an ad hoc version of `itertools.zip_longest()` which merges the files `calls.json` and `messages.json` in chronological order and filters by date and contact; the latter outputs the merged list in TXT, HTML, or JSON format. The dates, contacts, and output format are specified by command line options.

```
client_logs/
media/
voicemail/
calls.json
central.json
inventory.json
ips.json
messages.json
user_profile.json
user_shard.json
```

The pertinent files used by the script are:

- `calls.json`, a list of objects having the following form
```
  {
    "start_time": "2016-06-06T22:13:18.000+00:00",
    "duration": 128.0,
    "caller": "+1503888525",
    "called": "+1503756462"
  }
```

- `messages.json`, also a list of objects
```
  {
    "username": "petergrace",
    "device_id": "",
    "direction": 1,
    "contact_value": "+1503890217",
    "contact_name": "1 (503) 890-2176",
    "date": "2016-03-20T00:52:05.000Z",
    "message": "Ok. Stop by and see it later when you can.",
    "read": 1,
    "deleted": 0
  }
```

- `user_shard.json`, a single object containing a list of contact objects
```
  {
    "users": [...],
    "user_attributes": [...],
    "sessions": [...],
    "subscriptions": [...],
    "identities": [...],
    "devices": [...],
    "contacts": [
      {
        "contact_value": "+1503890217",
        "name": "Unknown"
      },
        ...
    ]
  }
```

- `media/`, a directory containing messages other than text messages, and voicemails from restricted numbers. Files are in the following formats: 3GPP, PDF, AMR, GIF, JPEG, PNG, MP4, VCARD, WAV, X-WAV

- `voicemail/`, a directory containing only WAV files.
