# tde -- TextNow Data Extractor
A Python script to extract the call and text message history from a TextNow data disclosure package, and output it in human-readable format. An explanation of the necessity of the script can be found in [the project wiki](https://github.com/petergrace1618/textnow-data-extractor/wiki).

The data disclosure package has the following structure.

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

- `calls.json` which is an array of objects of the form
```
  {
    "start_time": "2016-06-06T22:13:18.000+00:00",
    "duration": 128.0,
    "caller": "+1503888525",
    "called": "+1503756462"
  }
```
- `messages.json`, also an array of objects of the form
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
- `user_shard.json`, a single object which contains an array of contact objects
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

- `media/` which contains files of the following formats: 3GPP, PDF, AMR, GIF, JPEG, PNG, MP4, VCARD, WAV, X-WAV

- `voicemail/` which contains only WAV files.
