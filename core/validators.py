from typing import List, Dict, Optional, Tuple, Set
from django.core.validators import BaseValidator
import re

from django.apps import apps
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import validate_ipv4_address

import logging

logger = logging.getLogger(__name__)


def validate_penalty_value(value):
    """Validate penalty value: empty, absolute (10) or relative (+3, -2)."""
    if value == "":
        return
    if not re.match(r"^[+-]?\d{1,3}$", value):
        raise ValidationError(
            "Value must be empty, an integer (e.g. 10), or relative (e.g. +3, -2)"
        )


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


def validate_ael_variable_name(value):
    """Validator for AEL global variable name."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        raise ValidationError(
            "Variable name must start with a letter or underscore, "
            "and contain only letters, digits, and underscores."
        )


def validate_ael_variable_value(value):
    """Reject characters that would break AEL globals block syntax."""
    if re.search(r"[;\r\n]", value):
        raise ValidationError(
            "Variable value must not contain ';' or line breaks."
        )


def validate_match_hosts(value):
    """Validate comma-separated list of hosts/IPs without ports for pjsip identify match=."""
    if not value:
        return
    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # Reject host:port (bare colon = port separator)
        if ":" in entry and not entry.startswith("["):
            raise ValidationError(
                _("'%(value)s' must not contain a port — use plain IP or hostname (for IPv6 use bracket notation, e.g. [::1])"),
                params={"value": entry},
            )
        # Reject [ipv6]:port — bracket prefix alone is not enough
        if entry.startswith("[") and "]:" in entry:
            raise ValidationError(
                _("'%(value)s' must not contain a port — use [::1] without port suffix"),
                params={"value": entry},
            )


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

    # Special Asterisk extension names
    if value in ("s", "t", "i", "h"):
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
    """Django validator for Asterisk dialplan steps"""

    message = "Invalid Asterisk dialplan syntax: %(error)s"
    code = "invalid_dialplan_syntax"

    # Allowed Asterisk applications
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
        "ConfBridge",
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
        "PauseQueueMember",
        "UnPauseQueueMember",
        "ChanSpy",
        "ExtenSpy",
    }

    # Block keywords for AEL
    BLOCK_KEYWORDS = {"if", "else", "while", "for", "switch"}
    CONDITION_OPERATORS = {"==", "!=", ">", "<", ">=", "<=", "&&", "||", "!"}

    def __init__(self, limit_value=None, allowed_macros: Optional[Set[str]] = None):
        """
        Initialize validator

        Args:
            limit_value: Not used, kept for BaseValidator compatibility
            allowed_macros: Set of allowed macro names that can be called in dialplan
        """
        super().__init__(limit_value)
        self.allowed_macros = allowed_macros or set()

    def __call__(self, value):
        """Validates Asterisk dialplan steps"""
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
        """Validates dialplan steps with support for block constructs"""
        if not dialplan_content.strip():
            raise ValidationError("Empty dialplan content")

        # Preprocessing - remove extra spaces but preserve structure
        lines = dialplan_content.split("\n")
        processed_lines = []

        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if stripped_line:
                processed_lines.append((i + 1, stripped_line))

        if not processed_lines:
            raise ValidationError("Dialplan contains no steps")

        # Parse with block construct support
        self.parse_block_structure(processed_lines)

    def parse_block_structure(self, lines: List[Tuple[int, str]]):
        """Parses block structure of AEL (if/else/while etc.)"""
        i = 0
        while i < len(lines):
            line_num, line = lines[i]

            try:
                if self.is_block_start(line):
                    i = self.parse_block(lines, i)
                else:
                    self.validate_dialplan_step(line, line_num)
                    i += 1
            except ValidationError as e:
                raise ValidationError(f"Line {line_num}: {str(e)}")

    def is_block_start(self, line: str) -> bool:
        """Checks if line is the start of a block"""
        line_lower = line.lower().strip()

        # Check if constructs
        if line_lower.startswith("if") and "(" in line and "{" in line:
            return True

        # Check else
        if line_lower.startswith("else") and "{" in line:
            return True

        # Check else too
        if line_lower.startswith("}") and "else" in line and "{" in line:
            return True

        # Check while, for
        for keyword in ["while", "for"]:
            if line_lower.startswith(keyword) and "(" in line and "{" in line:
                return True

        return False

    def _find_matching_paren(self, text: str, start_pos: int) -> int:
        """Finds the position of closing ) that matches ( at start_pos"""
        if text[start_pos] != "(":
            return -1

        depth = 0
        in_string = False
        quote_char = None

        for i in range(start_pos, len(text)):
            char = text[i]

            # Handle string boundaries
            if not in_string and char in "\"'":
                in_string = True
                quote_char = char
            elif in_string and char == quote_char:
                if i > 0 and text[i - 1] != "\\":
                    in_string = False
                    quote_char = None

            elif not in_string:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        return i

        return -1

    def _count_structural_braces(self, text: str) -> int:
        """Counts structural braces (not inside quotes or ${} variable references)"""
        count = 0
        i = 0
        in_string = False
        quote_char = None
        var_depth = 0  # Track ${} nesting

        while i < len(text):
            char = text[i]

            # Handle string boundaries
            if not in_string and char in "\"'":
                in_string = True
                quote_char = char
            elif in_string and char == quote_char:
                # Check for escaped quote
                if i > 0 and text[i - 1] != "\\":
                    in_string = False
                    quote_char = None

            # Handle ${} variable references
            elif not in_string:
                if i < len(text) - 1 and text[i : i + 2] == "${":
                    var_depth += 1
                    i += 1  # Skip the $
                elif char == "}" and var_depth > 0:
                    var_depth -= 1
                elif char == "{" and var_depth == 0:
                    count += 1
                elif char == "}" and var_depth == 0:
                    count -= 1

            i += 1

        return count

    def parse_block(self, lines: List[Tuple[int, str]], start_idx: int) -> int:
        """Parses block construct and returns index after the block"""
        line_num, line = lines[start_idx]

        # Validate block header
        self.validate_block_header(line, line_num)

        # Find block body - count only structural braces
        brace_count = self._count_structural_braces(line)
        current_idx = start_idx + 1

        while current_idx < len(lines) and brace_count > 0:
            inner_line_num, inner_line = lines[current_idx]

            # Check for nested blocks BEFORE counting braces
            if self.is_block_start(inner_line):
                # Nested block - parse it completely and skip those lines
                current_idx = self.parse_block(lines, current_idx)
                continue

            # Count structural braces only for non-block lines
            brace_count += self._count_structural_braces(inner_line)

            if brace_count > 0:  # Still inside the block
                if inner_line.strip() == "}":
                    # Just closing brace
                    pass
                else:
                    # Regular step
                    self.validate_dialplan_step(inner_line, inner_line_num)

            current_idx += 1

        if brace_count != 0:
            raise ValidationError(
                f"Unbalanced braces in block starting at line {line_num}"
            )

        # Check if there's an else after if
        if current_idx < len(lines):
            next_line_num, next_line = lines[current_idx]
            if next_line.lower().strip().startswith("else"):
                return self.parse_block(lines, current_idx)

        return current_idx

    def validate_block_header(self, line: str, line_num: int):
        """Validates block header (if, else, while etc.)"""
        line_stripped = line.strip()

        if line_stripped.lower().startswith("if"):
            self.validate_if_condition(line_stripped, line_num)
        elif line_stripped.lower().startswith("else"):
            self.validate_else_statement(line_stripped, line_num)
        elif line_stripped.lower().startswith("while"):
            self.validate_while_condition(line_stripped, line_num)
        elif line_stripped.lower().startswith("for"):
            self.validate_for_loop(line_stripped, line_num)

    def validate_if_condition(self, line: str, line_num: int):
        """Validates if condition"""
        # Expected format: if (condition) {
        if not line.startswith("if"):
            raise ValidationError("IF statement must start with 'if'")

        # Find condition in parentheses - need to find matching ) for the first (
        paren_start = line.find("(")
        if paren_start == -1:
            raise ValidationError("IF statement must have condition in parentheses")

        paren_end = self._find_matching_paren(line, paren_start)
        if paren_end == -1:
            raise ValidationError("IF statement must have condition in parentheses")

        condition = line[paren_start + 1 : paren_end].strip()
        if not condition:
            raise ValidationError("Condition in IF statement cannot be empty")

        # Validate condition
        self.validate_condition_expression(condition, line_num)

        # Check for opening brace
        if "{" not in line[paren_end:]:
            raise ValidationError("IF statement must have opening brace '{'")

    def validate_else_statement(self, line: str, line_num: int):
        """Validates else statement"""
        if not line.startswith("else"):
            raise ValidationError("ELSE statement must start with 'else'")

        # Check for opening brace
        if "{" not in line:
            raise ValidationError("ELSE statement must have opening brace '{'")

    def validate_while_condition(self, line: str, line_num: int):
        """Validates while condition"""
        if not line.startswith("while"):
            raise ValidationError("WHILE statement must start with 'while'")

        # Find condition in parentheses - need to find matching ) for the first (
        paren_start = line.find("(")
        if paren_start == -1:
            raise ValidationError("WHILE statement must have condition in parentheses")

        paren_end = self._find_matching_paren(line, paren_start)
        if paren_end == -1:
            raise ValidationError("WHILE statement must have condition in parentheses")

        condition = line[paren_start + 1 : paren_end].strip()
        if not condition:
            raise ValidationError("Condition in WHILE statement cannot be empty")

        self.validate_condition_expression(condition, line_num)

        if "{" not in line[paren_end:]:
            raise ValidationError("WHILE statement must have opening brace '{'")

    def validate_for_loop(self, line: str, line_num: int):
        """Validates for loop"""
        if not line.startswith("for"):
            raise ValidationError("FOR statement must start with 'for'")

        # FOR loops in AEL have format: for (init; condition; increment)
        paren_start = line.find("(")
        if paren_start == -1:
            raise ValidationError("FOR statement must have parameters in parentheses")

        paren_end = self._find_matching_paren(line, paren_start)
        if paren_end == -1:
            raise ValidationError("FOR statement must have parameters in parentheses")

        for_params = line[paren_start + 1 : paren_end].strip()
        if not for_params:
            raise ValidationError("FOR statement must have parameters")

        if "{" not in line[paren_end:]:
            raise ValidationError("FOR statement must have opening brace '{'")

    def validate_condition_expression(self, condition: str, line_num: int):
        """Validates condition expression"""
        if not condition.strip():
            raise ValidationError("Condition cannot be empty")

        # Check balance of parentheses in condition
        paren_count = 0
        brace_count = 0
        quote_char = None

        for char in condition:
            if char in ['"', "'"] and quote_char is None:
                quote_char = char
            elif char == quote_char:
                quote_char = None
            elif quote_char is None:
                if char == "(":
                    paren_count += 1
                elif char == ")":
                    paren_count -= 1
                elif char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1

        if paren_count != 0:
            raise ValidationError("Unbalanced parentheses in condition")

        if brace_count != 0:
            raise ValidationError("Unbalanced braces in condition")

        if quote_char is not None:
            raise ValidationError("Unclosed quote in condition")

        # Check if condition contains at least one comparison operator or variable
        has_comparison = any(op in condition for op in self.CONDITION_OPERATORS)
        has_variable = "${" in condition or condition.strip().isdigit()
        has_function_call = "(" in condition and ")" in condition

        if not (has_comparison or has_variable or has_function_call):
            raise ValidationError(
                "Condition must contain comparison operator, variable or function call"
            )

    def validate_dialplan_step(self, step: str, line_num: int):
        """Validates individual dialplan step"""
        step = step.strip()

        if not step:
            return

        # Skip comments
        if step.startswith("//") or step.startswith("/*") or step.startswith(";"):
            return

        # Skip closing braces
        if step == "}":
            return

        # Check block constructs (they shouldn't have ;)
        if self.is_block_start(step):
            raise ValidationError("Block constructs should be handled separately")

        # Check if step ends with semicolon
        if not step.endswith(";"):
            raise ValidationError(f"Step must end with semicolon: '{step}'")

        # Remove semicolon for analysis
        step_content = step[:-1].strip()

        # Analyze application call
        self.parse_application_call(step_content, line_num)

    def parse_application_call(self, step_content: str, line_num: int):
        """Parses Asterisk application call"""
        if not step_content:
            raise ValidationError("Empty step")

        # Check for macro calls first
        if self.is_macro_call(step_content):
            self.validate_macro_call(step_content, line_num)
            return

        # Check for AEL-style variable assignment (e.g., VOICE=${RAND(1,2)})
        if self.is_variable_assignment(step_content):
            self.validate_variable_assignment(step_content, line_num)
            return

        # Check for AEL control flow statements
        if step_content in ("return", "break", "continue"):
            return

        if step_content.startswith("goto "):
            # goto context,extension,priority or goto extension,priority or goto priority
            return

        # Check format application(parameters)
        if "(" in step_content:
            # Find application name
            paren_pos = step_content.find("(")
            app_name = step_content[:paren_pos].strip()

            # Check if it's allowed Asterisk application
            if app_name not in self.ASTERISK_APPLICATIONS:
                raise ValidationError(f"Unknown Asterisk application '{app_name}'")

            # Check correct parentheses
            if not step_content.endswith(")"):
                raise ValidationError("Application call must end with parenthesis ')'")

            # Extract parameters
            params_part = step_content[paren_pos + 1 : -1]
            self.validate_parameters(params_part, app_name, line_num)

        else:
            # If no parentheses, it might be simple call without parameters
            if step_content not in self.ASTERISK_APPLICATIONS:
                raise ValidationError(
                    f"Unknown Asterisk application or incorrect format: '{step_content}'"
                )

    def is_macro_call(self, step_content: str) -> bool:
        """Checks if step is a macro call"""
        # AEL macro calls use & prefix: &MacroName(), &MacroName(params)
        # Also support: MacroName(), MacroName(params), or just MacroName
        if not self.allowed_macros:
            return False

        # Extract potential macro name
        content = step_content.strip()

        # Handle AEL-style & prefix
        if content.startswith("&"):
            content = content[1:]

        if "(" in content:
            macro_name = content.split("(")[0].strip()
        else:
            macro_name = content.strip()

        return macro_name in self.allowed_macros

    def validate_macro_call(self, step_content: str, line_num: int):
        """Validates macro call"""
        content = step_content.strip()

        # Handle AEL-style & prefix
        if content.startswith("&"):
            content = content[1:]

        if "(" in content:
            paren_pos = content.find("(")
            macro_name = content[:paren_pos].strip()

            if macro_name not in self.allowed_macros:
                raise ValidationError(
                    f"Unknown macro '{macro_name}'. Allowed macros: {', '.join(sorted(self.allowed_macros))}"
                )

            # Check correct parentheses
            if not content.endswith(")"):
                raise ValidationError("Macro call must end with parenthesis ')'")

            # Extract and validate parameters
            params_part = content[paren_pos + 1 : -1]
            self.validate_macro_parameters(params_part, macro_name, line_num)
        else:
            # Simple macro call without parameters
            macro_name = content.strip()
            if macro_name not in self.allowed_macros:
                raise ValidationError(
                    f"Unknown macro '{macro_name}'. Allowed macros: {', '.join(sorted(self.allowed_macros))}"
                )

    def validate_macro_parameters(
        self, params_str: str, macro_name: str, line_num: int
    ):
        """Validates macro parameters"""
        if not params_str.strip():
            return  # Empty parameters are allowed

        # Check balance of brackets and quotes
        self.check_balanced_brackets_and_quotes(params_str, line_num)

        # Parse parameters (considering nested brackets and quotes)
        params = self.parse_parameters(params_str)

        # Basic validation - macros can have any parameters
        for i, param in enumerate(params):
            if not param.strip():
                raise ValidationError(
                    f"Parameter {i+1} in macro '{macro_name}' cannot be empty"
                )

    def is_variable_assignment(self, step_content: str) -> bool:
        """Checks if step is an AEL-style variable assignment (e.g., VOICE=${RAND(1,2)})"""
        if "=" not in step_content:
            return False

        # Find = position (must be outside brackets and quotes)
        eq_pos = self._find_assignment_operator(step_content)
        if eq_pos == -1:
            return False

        # Left side must be valid variable name
        left_side = step_content[:eq_pos].strip()

        # Variable names: letters, digits, underscore, can't start with digit
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", left_side))

    def _find_assignment_operator(self, text: str) -> int:
        """Finds = position outside brackets/quotes, excluding == comparison"""
        depth = 0
        in_string = False
        quote_char = None

        i = 0
        while i < len(text):
            char = text[i]

            if in_string:
                if char == quote_char and (i == 0 or text[i - 1] != "\\"):
                    in_string = False
            elif char in "\"'":
                in_string = True
                quote_char = char
            elif char in "({":
                depth += 1
            elif char in ")}":
                depth -= 1
            elif char == "=" and depth == 0:
                # Check it's not == (comparison operator)
                if i + 1 < len(text) and text[i + 1] == "=":
                    i += 1  # Skip ==
                elif i > 0 and text[i - 1] in "!<>":
                    pass  # Part of !=, <=, >= - not assignment
                else:
                    return i
            i += 1

        return -1

    def validate_variable_assignment(self, step_content: str, line_num: int):
        """Validates AEL-style variable assignment"""
        eq_pos = self._find_assignment_operator(step_content)

        # Validate right side (the value) has balanced brackets/quotes
        right_side = step_content[eq_pos + 1 :].strip()
        if right_side:
            self.check_balanced_brackets_and_quotes(right_side, line_num)

    def validate_parameters(self, params_str: str, app_name: str, line_num: int):
        """Validates application parameters"""
        if not params_str.strip():
            return  # Empty parameters are allowed

        # Check balance of brackets and quotes
        self.check_balanced_brackets_and_quotes(params_str, line_num)

        # Parse parameters (considering nested brackets and quotes)
        params = self.parse_parameters(params_str)

        # Additional validation for specific applications
        self.validate_specific_application_params(app_name, params, line_num)

    def check_balanced_brackets_and_quotes(self, text: str, line_num: int):
        """Checks balance of brackets and quotes"""
        stack = []
        quote_char = None
        i = 0

        while i < len(text):
            char = text[i]

            # Handle quotes
            if char in ['"', "'"] and quote_char is None:
                quote_char = char
            elif char == quote_char:
                quote_char = None
            elif quote_char is not None:
                # Inside quotes - skip everything
                i += 1
                continue

            # Handle brackets (only outside quotes)
            elif quote_char is None:
                if char in "([{":
                    stack.append(char)
                elif char in ")]}":
                    if not stack:
                        raise ValidationError(f"Unbalanced bracket '{char}'")

                    last = stack.pop()
                    pairs = {"(": ")", "[": "]", "{": "}"}
                    if pairs.get(last) != char:
                        raise ValidationError(
                            f"Incorrect bracket pair: '{last}' and '{char}'"
                        )

            i += 1

        if stack:
            raise ValidationError(f"Unclosed bracket: '{stack[-1]}'")

        if quote_char:
            raise ValidationError(f"Unclosed quote: '{quote_char}'")

    def parse_parameters(self, params_str: str) -> List[str]:
        """Parses parameters considering nested structures"""
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
        """Specific validation for individual applications"""

        # Validation for AGI
        if app_name == "AGI":
            if not params:
                raise ValidationError("AGI requires at least one parameter (script)")

            script_param = params[0]
            if not script_param:
                raise ValidationError("AGI script parameter cannot be empty")

        # Validation for Dial
        elif app_name == "Dial":
            if not params:
                raise ValidationError(
                    "Dial requires at least one parameter (destination)"
                )

        # Validation for ConfBridge
        elif app_name == "ConfBridge":
            if not params:
                raise ValidationError(
                    "ConfBridge requires at least one parameter (conference room number)"
                )

        # Validation for Playback
        elif app_name == "Playback":
            if not params:
                raise ValidationError(
                    "Playback requires at least one parameter (filename)"
                )

        # Validation for Wait
        elif app_name == "Wait":
            if params:
                wait_time = params[0]
                # Check if it's number or variable
                if not (
                    wait_time.isdigit()
                    or "${" in wait_time
                    or wait_time.replace(".", "").isdigit()
                ):
                    raise ValidationError("Wait parameter must be number or variable")


# Helper functions
class DialplanHelper:
    """Helper for working with dialplan"""

    @staticmethod
    def parse_dialplan_steps(dialplan_text: str) -> List[Dict[str, str]]:
        """Parses dialplan text and returns structured steps"""
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
    def validate_dialplan(
        dialplan_text: str, allowed_macros: Optional[Set[str]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validates dialplan and returns (is_valid, error_message)"""
        try:
            validator = AsteriskDialplanValidator(allowed_macros=allowed_macros)
            validator(dialplan_text)
            return True, None
        except ValidationError as e:
            return False, str(e)

    @staticmethod
    def format_dialplan(steps: List[str]) -> str:
        """Formats list of steps into proper dialplan"""
        formatted_steps = []
        for step in steps:
            step = step.strip()
            if not step.endswith(";"):
                step += ";"
            formatted_steps.append(step)
        return "\n".join(formatted_steps)


def validate_dialplan_field(value):
    """Model-level dialplan validator.

    Resolves the set of allowed macros from the database at call time (so it
    stays in sync with `DialplanMacro` rows) and delegates to
    `AsteriskDialplanValidator`. Attach this to `DialplanExtension.dialplan` so
    that imports and management commands are validated the same way the admin
    form is, not only the form's `clean_dialplan`.
    """
    DialplanMacro = apps.get_model("core", "DialplanMacro")
    allowed_macros = set(DialplanMacro.objects.values_list("name", flat=True))
    AsteriskDialplanValidator(allowed_macros=allowed_macros)(value)
