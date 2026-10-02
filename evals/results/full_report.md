## Overall

| Mode | Success | Rate (95% CI) | Steps (median, success) | Time/run s (median) | Tokens/run (median) | Errors |
|---|---|---|---|---|---|---|
| tree | 54/60 | 90% (80–95%) | 5.0 | 20.6 | 22234 | 1 |
| screenshot | 14/60 | 23% (14–35%) | 6.0 | 187.7 | 151713 | 9 |
| screenshot_raw | 52/60 | 87% (76–93%) | 4.0 | 23.1 | 20445 | 4 |

## Excluding errored runs

| Mode | Success | Rate (95% CI) |
|---|---|---|
| tree | 54/59 | 92% (82–96%) |
| screenshot | 14/51 | 27% (17–41%) |
| screenshot_raw | 52/56 | 93% (83–97%) |

## Paired vs tree (same task, same trial)

| Mode | Both pass | Only tree | Only this mode | Both fail | Exact McNemar p |
|---|---|---|---|---|---|
| screenshot | 14 | 40 | 0 | 6 | 1.82e-12 |
| screenshot_raw | 50 | 4 | 2 | 4 | 0.688 |

## How runs ended

| Mode | done ✓ | done ✗ (claimed, check failed) | stuck | timeout | hard_stuck | error |
|---|---|---|---|---|---|---|
| tree | 53 | 1 | 0 | 5 | 0 | 1 |
| screenshot | 14 | 1 | 0 | 36 | 0 | 9 |
| screenshot_raw | 52 | 1 | 0 | 3 | 0 | 4 |

## Per task (passes / runs)

| Task | tree | screenshot | screenshot_raw |
|---|---|---|---|
| bold_text | 3/3 | 0/3 | 3/3 |
| increase_contrast | 3/3 | 0/3 | 3/3 |
| button_borders | 3/3 | 0/3 | 3/3 |
| reduce_motion | 3/3 | 0/3 | 3/3 |
| reduce_transparency | 3/3 | 0/3 | 3/3 |
| speak_selection | 3/3 | 0/3 | 3/3 |
| dark_mode | 3/3 | 0/3 | 3/3 |
| text_size_up | 0/3 | 0/3 | 0/3 |
| ios_version | 3/3 | 1/3 | 3/3 |
| kate_email | 3/3 | 3/3 | 3/3 |
| contact_phone | 3/3 | 0/3 | 1/3 |
| contact_email | 3/3 | 0/3 | 2/3 |
| contact_delete | 3/3 | 0/3 | 3/3 |
| reminder_new | 3/3 | 2/3 | 3/3 |
| reminder_priority | 3/3 | 0/3 | 2/3 |
| reminder_list | 3/3 | 0/3 | 3/3 |
| calendar_event | 0/3 | 0/3 | 2/3 |
| wiki_article | 3/3 | 2/3 | 3/3 |
| maps_place | 3/3 | 3/3 | 3/3 |
| settings_about | 3/3 | 3/3 | 3/3 |
