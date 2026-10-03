## Overall

| Mode | Success | Rate (95% CI) | Steps (median, success) | Time/run s (median) | Tokens/run (median) | Errors |
|---|---|---|---|---|---|---|
| tree | 28/39 | 72% (56–83%) | 6.5 | 42.9 | 32443 | 0 |
| screenshot_raw | 17/20 | 85% (64–95%) | 10.5 | 67.7 | 55732 | 4 |
| tree_old_executor | 11/20 | 55% (34–74%) | 11.0 | 63.6 | 45712 | 0 |
| screenshot_ocr | 13/18 | 72% (49–88%) | 7.0 | 58.6 | 46367 | 2 |
| screenshot_raw@gemini-3.1-pro-preview | 15/18 | 83% (61–94%) | 9.0 | 128.9 | 47440 | 2 |

## Excluding errored runs

| Mode | Success | Rate (95% CI) |
|---|---|---|
| tree | 28/39 | 72% (56–83%) |
| screenshot_raw | 16/16 | 100% (81–100%) |
| tree_old_executor | 11/20 | 55% (34–74%) |
| screenshot_ocr | 13/16 | 81% (57–93%) |
| screenshot_raw@gemini-3.1-pro-preview | 15/16 | 94% (72–99%) |

## Paired vs tree (same task, same trial)

| Mode | Both pass | Only tree | Only this mode | Both fail | Exact McNemar p |
|---|---|---|---|---|---|
| screenshot_raw | 12 | 2 | 5 | 1 | 0.453 |
| tree_old_executor | 9 | 5 | 2 | 4 | 0.453 |
| screenshot_ocr | 12 | 1 | 1 | 4 | 1 |
| screenshot_raw@gemini-3.1-pro-preview | 12 | 1 | 3 | 2 | 0.625 |

## How runs ended

| Mode | done ✓ | done ✗ (claimed, check failed) | stuck | timeout | hard_stuck | error |
|---|---|---|---|---|---|---|
| tree | 25 | 7 | 0 | 7 | 0 | 0 |
| screenshot_raw | 12 | 0 | 0 | 4 | 0 | 4 |
| tree_old_executor | 9 | 6 | 0 | 5 | 0 | 0 |
| screenshot_ocr | 11 | 1 | 0 | 4 | 0 | 2 |
| screenshot_raw@gemini-3.1-pro-preview | 14 | 1 | 0 | 1 | 0 | 2 |

## Per task (passes / runs)

| Task | tree | screenshot_raw | tree_old_executor | screenshot_ocr | screenshot_raw@gemini-3.1-pro-preview |
|---|---|---|---|---|---|
| h_contact_full | 2/3 | 2/2 | 1/2 | 1/2 | 2/2 |
| h_contact_two_phones | 3/3 | 2/2 | 1/2 | 2/2 | 1/2 |
| h_contact_add_email | 3/3 | 1/2 | 2/2 | 2/2 | 2/2 |
| h_contact_company | 3/3 | 1/2 | 0/2 | 2/2 | 2/2 |
| h_contact_delete_two | 2/3 | 2/2 | 2/2 | 2/2 | 2/2 |
| h_reminder_in_list | 3/3 | 2/2 | 2/2 | 1/1 | 1/1 |
| h_reminder_two | 2/3 | 2/2 | 2/2 | 1/1 | 1/1 |
| h_reminder_flagged | 0/3 | 0/1 | 0/1 | 0/1 | 0/1 |
| h_reminder_note | 2/3 | 1/1 | 0/1 | 0/1 | 1/1 |
| h_settings_two_pages | 3/3 | 1/1 | 0/1 | 1/1 | 1/1 |
| h_settings_three_pages | 2/3 | 1/1 | 0/1 | 0/1 | 1/1 |
| h_calendar_allday | 0/3 | 1/1 | 0/1 | 0/1 | 0/1 |
| h_daniel_phones | 3/3 | 1/1 | 1/1 | 1/1 | 1/1 |
