# TODO PEARLPBX2

### Parking 
 - Вияснити які частини зараз задіяні в ulines/parking
 - що я випадково видалив в розділ express? 
 - до PearlPBX-таблиці маршрутизації додати службовий контекст Parking де, 
0 - (трансфер на ноль паркує дзвінок по вказаній змінній PARKING_LINE в каналі, а якщо її немає, то про це треба повідомити або просто скинути дзвінок) 
1 - 199 (спроба дістати дзвінок з паркінгу за вказаною ${EXTEN}-коміркою. Якщо дзвінка там немає, то так і сказати (здається є службовий файл invalid-parking чи щось таке)  
трансфер на 1-199 теж має право на життя, якщо користувач самостійно обирає номер лінії. Якзо вона не зайнята, звісно іншим дзвінком. 
Треба це все якось синхронизувати з існуючою системою виділення паркінгу (redis?) 


### Web Phone
- Partially implemented
- Update versions
- Integrate into Django

### Management of Sound files 
- Коли користувач видаляє файл або натискає на clear, файл фізично не видаляється - виправити 


### Зменшити час на ручну роботу при новій інсталляції 
- Знайти спосіб автоматизувати хоча б українськи інсталляції, які мені відомі.
- Можливо створити TUI-скрипт? 


## Ціль

Після того, як закінчиться робота ansible install система має працювати "із коробки".
Користувачу треба показати, що йому завели адміна-суперкористувача, 10 SIP Users.
Показати де шукати паролі для цих користувачів і щоб вони могли дзвонити один одному,
з дащбордом, записом розмов (треба буде поміняти шаблони для внутрішніх дзвінків за замовчуванням), 
всі сервіси мають працювати і бути налаштованими. 

Треба ще спитати у користувача SLACK_WEBHOOK_URL для інформування адміна: 
- system_status 
- інші службові сервісі
- agi та dashboard_listener про missed_calls, unmatched_calls, etc. 


## Додаткові побажання 

Не завадить ціль ansible/update_asterisk, яка буде встановлювати останній LTS asterisk. 

### `call.answered` webhook event for non-queue (direct) calls

Currently `call.answered` (see `tasks/todo.md`) fires only from AMI
`AgentConnect`, which Asterisk's `app_queue` generates exclusively for calls
routed through a queue. A direct call to a specific extension (no queue)
never triggers `AgentConnect`, so today PearlPBX2 sends `call.incoming` and
`call.ended` for such calls but nothing in between — CRM has no "someone
picked up" signal for direct calls.

Likely extension point: `handle_dial_end()` in
`services/dashboard/dashboard_listener.py` already receives AMI `DialEnd`
with `DialStatus` (published internally as `channel_dial_end`, not yet wired
to webhooks). When `DialStatus == "ANSWER"`, that's the direct-call
equivalent of `AgentConnect`.

Open design questions for when this is picked up:
- Reuse the same `call.answered` event (with `queue: null`) or introduce a
  distinct event, since the data source differs (dial-leg channel/number,
  not a queue member interface)?
- Who answered — need to resolve the number/channel from `DialBegin`'s
  `DestChannel`/`Channel`, not `Member`/`Interface` (those are queue-only
  AMI fields).
- Whether `send_answered` should gain a "direct calls" toggle alongside
  the existing queue filter, since right now `send_answered` requires ≥1
  queue selected.

### SIPUser extension hijack scenario (structural fix needed)

`SIPUser.save()` знаходить пов'язаний `DialplanExtension` за текстовим `ext`
(`previous_extension`), а не за явним FK. Якщо два SIPUser по черзі
використовують той самий `previous_extension`, другий `save()` може
захопити/переписати extension, що належить першому. Потребує явного
`ForeignKey` від `DialplanExtension` до `SIPUser` замість пошуку за текстом —
більша структурна зміна, окремий раунд (не займатись у M12 medium-фіксах).

