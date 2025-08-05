from django.core.validators import BaseValidator
from typing import List, Dict, Optional, Tuple
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import validate_ipv4_address

import logging

logger = logging.getLogger(__name__)


def validate_bind_ip(value):
    items = value.split(":")
    logger.info(value)
    validate_ipv4_address(items[0])
    if len(items) > 1:
        try:
            port = int(items[1])
            if port < 1024 or port > 65535:
                raise ValidationError(
                    _("%(value)s is not a valid port"),
                    params={"value": items[1]},
                )
        except ValueError:
            raise ValidationError(
                _("%(value)s is not a valid port"),
                params={"value": items[1]},
            )


def validate_asterisk_context(value):
    """Validator for Asterisk context name"""
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*$", value):
        raise ValidationError(
            "Context name must start with letter or underscore, "
            "and contain only letters, digits, underscores, and hyphens."
        )
    if len(value) > 80:
        raise ValidationError("Context name is too long (max 80 characters).")


def validate_asterisk_extension_prefix(value):
    """
    Validator for Asterisk extension prefix (dialplan pattern).

    Asterisk pattern matching rules:
    - Starts with _ (underscore)
    - X - any digit 0-9
    - Z - any digit 1-9
    - N - any digit 2-9
    - [123] - one of the digits in brackets
    - [1-5] - digit range
    - . (dot) - one or more characters
    - ! (exclamation mark) - zero or more characters
    - Literals (digits, +, -, etc.)
    """

    if not value:
        return

    # Check if the value contains only digits
    if value.isdigit():
        # If the value is all digits, it is a valid pattern
        return

    # Check that it starts with _
    if not value.startswith("_"):
        raise ValidationError(
            _('Asterisk extension pattern must start with the "_" character'),
            code="missing_underscore",
        )

    # Remove the first character _ for further validation
    pattern = value[1:]

    if not pattern:
        raise ValidationError(
            _('Pattern cannot be empty after "_"'), code="empty_pattern"
        )

    # Regular expression for validating Asterisk pattern
    # Allowed characters: digits, X, Z, N, [ranges], +, -, ., !, spaces
    asterisk_pattern_regex = r"^[0-9XZN\[\]0-9\-\+\.\!\s]*$"

    if not re.match(asterisk_pattern_regex, pattern):
        raise ValidationError(
            _(
                "Invalid characters in pattern. Allowed: digits, X, Z, N, [ranges], +, -, ., !"
            ),
            code="invalid_characters",
        )

    # Check for correct square brackets usage
    if "[" in pattern or "]" in pattern:
        bracket_count = pattern.count("[")
        closing_bracket_count = pattern.count("]")

        if bracket_count != closing_bracket_count:
            raise ValidationError(
                _("Unbalanced square brackets in pattern"), code="unbalanced_brackets"
            )

        # Check that all opening brackets have corresponding closing brackets
        bracket_pairs = re.findall(r"\[[^\]]*\]", pattern)
        for pair in bracket_pairs:
            content = pair[1:-1]
            if not content:
                raise ValidationError(
                    _("Empty square brackets are not allowed"), code="empty_brackets"
                )

            # Check ranges like [1-9]
            if "-" in content:
                parts = content.split("-")
                if len(parts) == 2:
                    try:
                        start, end = int(parts[0]), int(parts[1])
                        if start >= end or start < 0 or end > 9:
                            raise ValidationError(
                                _("Invalid range in brackets: %(content)s"),
                                params={"content": pair},
                                code="invalid_range",
                            )
                    except (ValueError, IndexError):
                        raise ValidationError(
                            _("Invalid range format: %(content)s"),
                            params={"content": pair},
                            code="invalid_range_format",
                        )

    # Check maximum length (Asterisk has a limit)
    if len(value) > 80:
        raise ValidationError(
            _("Pattern is too long (maximum 80 characters)"), code="too_long"
        )

    # Additional checks for common mistakes

    # Check that . and ! are not doubled after other special symbols
    if ".." in pattern or "!!" in pattern:
        raise ValidationError(
            _("Double wildcards (.., !!) are not recommended"), code="double_wildcards"
        )

    # Warning about potentially problematic patterns
    if pattern.endswith("X.") or pattern.endswith("Z.") or pattern.endswith("N."):
        # This is not an error, but may be undesirable
        pass


class AsteriskDialplanValidator(BaseValidator):
    """Django валідатор для Asterisk dialplan steps"""

    message = "Невірний синтаксис Asterisk dialplan: %(error)s"
    code = "invalid_dialplan_syntax"

    # Дозволені Asterisk applications
    ASTERISK_APPLICATIONS = {
        "Answer",
        "Dial",
        "Hangup",
        "Playback",
        "Background",
        "WaitExten",
        "Goto",
        "GotoIf",
        "Set",
        "NoOp",
        "Verbose",
        "Log",
        "Echo",
        "VoiceMail",
        "VoiceMailMain",
        "Queue",
        "AGI",
        "Busy",
        "Congestion",
        "Read",
        "SayNumber",
        "SayDigits",
        "DateTime",
        "Festival",
        "MixMonitor",
        "StopMixMonitor",
        "Record",
        "Wait",
        "System",
        "Return",
        "ExecIf",
        "While",
        "EndWhile",
        "For",
        "EndFor",
        "If",
        "ElseIf",
        "Else",
        "EndIf",
        "Switch",
        "Case",
        "Default",
        "EndSwitch",
        "Macro",
        "MacroExit",
        "GoSub",
        "GoSubIf",
        "Return",
        "StackPop",
        "UserEvent",
        "Progress",
        "Ringing",
        "SIPAddHeader",
        "SIPRemoveHeader",
        "SetCallerPres",
        "SetMusicOnHold",
        "StartMusicOnHold",
        "StopMusicOnHold",
        "WaitMusicOnHold",
        "SetAccount",
        "ResetCDR",
        "NoCDR",
        "ForkCDR",
        "Park",
        "ParkAndAnnounce",
        "ParkedCall",
        "UnparkCall",
        "PickupChan",
        "Pickup",
        "ChannelRedirect",
        "SendDTMF",
        "SendText",
        "SendImage",
        "ReceiveText",
        "GetCPEID",
        "Flash",
        "ZapRAS",
        "ZapSendKeypadFacility",
        "SetLanguage",
        "SayUnixTime",
        "SayPhonetic",
        "SayAlpha",
        "StripMSD",
        "Zapateller",
        "PrivacyManager",
        "Authenticate",
        "DBget",
        "DBput",
        "DBdel",
        "DBdeltree",
        "EAGI",
        "FastAGI",
        "DeadAGI",
        "Festival",
        "Flite",
        "Swift",
        "Cepstral",
        "SpeechCreate",
        "SpeechActivateGrammar",
        "SpeechStart",
        "SpeechBackground",
        "SpeechDeactivateGrammar",
        "SpeechProcessingSound",
        "SpeechDestroy",
        "MySQL",
        "ODBC",
        "Realtime",
        "Curl",
        "TrySystem",
        "VMAuthenticate",
        "VoiceMailPlayMsg",
        "MailboxExists",
        "HasVoicemail",
        "HasNewVoicemail",
        "SayCountPL",
        "Milliwatt",
        "TestServer",
        "TestClient",
        "WaitForRing",
        "WaitForSilence",
        "WaitForNoise",
        "BackgroundDetect",
        "TalkDetect",
        "Eval",
    }

    def __init__(self, allowed_macros=[], limit_value=None):
        super().__init__(limit_value)
        self.allowed_macros = allowed_macros

    def __call__(self, value):
        """Валідує Asterisk dialplan steps"""
        if not value:
            return

        try:
            self.validate_dialplan_steps(value)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                self.message, code=self.code, params={"error": str(e)}
            )

    def validate_dialplan_steps(self, dialplan_content: str):
        """Валідує кроки dialplan"""
        if not dialplan_content.strip():
            raise ValidationError("Порожній dialplan контент")

        # Розбиваємо на рядки та очищуємо
        lines = []
        for line in dialplan_content.split("\n"):
            line = line.strip()
            if line:  # Додаємо всі непорожні рядки
                lines.append(line)

        if not lines:
            raise ValidationError("Діалплан не містить кроків")

        for line_num, line in enumerate(lines, 1):
            try:
                self.validate_dialplan_step(line, line_num)
            except ValidationError as e:
                raise ValidationError(f"Рядок {line_num}: {str(e)}")

    def validate_dialplan_step(self, step: str, line_num: int):
        """Валідує окремий крок dialplan"""
        step = step.strip()

        if not step:
            return

        # Пропускаємо коментарі
        if step.startswith("//") or step.startswith("/*") or step.startswith(";"):
            return

        # Перевіряємо, чи закінчується крок крапкою з комою
        if not step.endswith(";"):
            raise ValidationError(
                f"Крок повинен закінчуватися крапкою з комою: '{step}'"
            )

        # Видаляємо крапку з комою для аналізу
        step_content = step[:-1].strip()

        # Аналізуємо application call
        self.parse_application_call(step_content, line_num)

    def parse_application_call(self, step_content: str, line_num: int):
        """Парсить виклик Asterisk application"""
        if not step_content:
            raise ValidationError("Порожній крок")

        # Перевіряємо формат application(parameters)
        if "(" in step_content:
            # Знаходимо назву application
            paren_pos = step_content.find("(")
            app_name = step_content[:paren_pos].strip()
            # Якщо перший символ &, то теж вирізати. То макрос.
            if app_name.startswith("&"):
                app_name = app_name[1:]

            # Перевіряємо, чи це дозволена Asterisk application
            if (
                app_name not in self.ASTERISK_APPLICATIONS
                and app_name not in self.allowed_macros
            ):
                raise ValidationError(
                    f"Невідома Asterisk application або macro '{app_name}'"
                )

            # Перевіряємо правильність дужок
            if not step_content.endswith(")"):
                raise ValidationError(
                    "Application виклик повинен закінчуватися дужкою ')'"
                )

            # Витягуємо параметри
            params_part = step_content[paren_pos + 1 : -1]
            self.validate_parameters(params_part, app_name, line_num)

        else:
            # Якщо немає дужок, це може бути простий виклик без параметрів
            if step_content not in self.ASTERISK_APPLICATIONS:
                raise ValidationError(
                    f"Невідома Asterisk application або неправильний формат: '{step_content}'"
                )

    def validate_parameters(self, params_str: str, app_name: str, line_num: int):
        """Валідує параметри application"""
        if not params_str.strip():
            return  # Порожні параметри допустимі

        # Перевіряємо баланс дужок і лапок
        self.check_balanced_brackets_and_quotes(params_str, line_num)

        # Парсимо параметри (враховуючи вкладені дужки та лапки)
        params = self.parse_parameters(params_str)

        # Додаткова валідація для специфічних applications
        self.validate_specific_application_params(app_name, params, line_num)

    def check_balanced_brackets_and_quotes(self, text: str, line_num: int):
        """Перевіряє збалансованість дужок і лапок"""
        stack = []
        quote_char = None
        i = 0

        while i < len(text):
            char = text[i]

            # Обробка лапок
            if char in ['"', "'"] and quote_char is None:
                quote_char = char
            elif char == quote_char:
                quote_char = None
            elif quote_char is not None:
                # Всередині лапок - пропускаємо все
                i += 1
                continue

            # Обробка дужок (тільки поза лапками)
            elif quote_char is None:
                if char in "([{":
                    stack.append(char)
                elif char in ")]}":
                    if not stack:
                        raise ValidationError(f"Незбалансована дужка '{char}'")

                    last = stack.pop()
                    pairs = {"(": ")", "[": "]", "{": "}"}
                    if pairs.get(last) != char:
                        raise ValidationError(
                            f"Неправильна пара дужок: '{last}' та '{char}'"
                        )

            i += 1

        if stack:
            raise ValidationError(f"Незакрита дужка: '{stack[-1]}'")

        if quote_char:
            raise ValidationError(f"Незакрита лапка: '{quote_char}'")

    def parse_parameters(self, params_str: str) -> List[str]:
        """Парсить параметри з врахуванням вкладених структур"""
        params = []
        current_param = ""
        paren_level = 0
        bracket_level = 0
        brace_level = 0
        quote_char = None

        for char in params_str:
            if char in ['"', "'"] and quote_char is None:
                quote_char = char
                current_param += char
            elif char == quote_char:
                quote_char = None
                current_param += char
            elif quote_char is not None:
                current_param += char
            else:
                if char == "(":
                    paren_level += 1
                elif char == ")":
                    paren_level -= 1
                elif char == "[":
                    bracket_level += 1
                elif char == "]":
                    bracket_level -= 1
                elif char == "{":
                    brace_level += 1
                elif char == "}":
                    brace_level -= 1
                elif (
                    char == ","
                    and paren_level == 0
                    and bracket_level == 0
                    and brace_level == 0
                ):
                    params.append(current_param.strip())
                    current_param = ""
                    continue

                current_param += char

        if current_param.strip():
            params.append(current_param.strip())

        return params

    def validate_specific_application_params(
        self, app_name: str, params: List[str], line_num: int
    ):
        """Специфічна валідація для окремих applications"""

        # Валідація для AGI
        if app_name == "AGI":
            if not params:
                raise ValidationError("AGI потребує принаймні один параметр (script)")

            script_param = params[0]
            if not script_param:
                raise ValidationError("AGI script параметр не може бути порожнім")

        # Валідація для Dial
        elif app_name == "Dial":
            if not params:
                raise ValidationError(
                    "Dial потребує принаймні один параметр (destination)"
                )

        # Валідація для Playback
        elif app_name == "Playback":
            if not params:
                raise ValidationError(
                    "Playback потребує принаймні один параметр (filename)"
                )

        # Валідація для Wait
        elif app_name == "Wait":
            if params:
                wait_time = params[0]
                # Перевіряємо, чи це число або змінна
                if not (
                    wait_time.isdigit()
                    or "${" in wait_time
                    or wait_time.replace(".", "").isdigit()
                ):
                    raise ValidationError(
                        "Wait параметр повинен бути числом або змінною"
                    )


# Допоміжні функції
class DialplanHelper:
    """Помічник для роботи з dialplan"""

    @staticmethod
    def parse_dialplan_steps(dialplan_text: str) -> List[Dict[str, str]]:
        """Парсить dialplan текст і повертає структуровані кроки"""
        steps = []

        for line_num, line in enumerate(dialplan_text.split("\n"), 1):
            line = line.strip()
            if not line or line.startswith("//") or line.startswith(";"):
                continue

            if not line.endswith(";"):
                continue

            step_content = line[:-1].strip()

            if "(" in step_content:
                paren_pos = step_content.find("(")
                app_name = step_content[:paren_pos].strip()
                params_str = (
                    step_content[paren_pos + 1 : -1]
                    if step_content.endswith(")")
                    else ""
                )

                steps.append(
                    {
                        "line": line_num,
                        "application": app_name,
                        "parameters": params_str,
                        "raw": line,
                    }
                )
            else:
                steps.append(
                    {
                        "line": line_num,
                        "application": step_content,
                        "parameters": "",
                        "raw": line,
                    }
                )

        return steps

    @staticmethod
    def validate_dialplan(dialplan_text: str) -> Tuple[bool, Optional[str]]:
        """Валідує dialplan і повертає (is_valid, error_message)"""
        try:
            validator = AsteriskDialplanValidator()
            validator(dialplan_text)
            return True, None
        except ValidationError as e:
            return False, str(e)

    @staticmethod
    def format_dialplan(steps: List[str]) -> str:
        """Форматує список кроків у правильний dialplan"""
        formatted_steps = []
        for step in steps:
            step = step.strip()
            if not step.endswith(";"):
                step += ";"
            formatted_steps.append(step)
        return "\n".join(formatted_steps)
