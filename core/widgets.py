from django import forms
from django.utils.html import escape
from django.utils.safestring import mark_safe


class PasswordWithToggleInput(forms.PasswordInput):
    template = """
        <div style="position: relative;">
            <input type="password" name="{name}" value="{value}" id="id_{name}" {attrs}/>
            <button type="button" onclick="togglePassword_{name}()" style="position: absolute; right: 0; top: 0;">👁</button>
            <button type="button" onclick="generatePassword_{name}()" style="position: absolute; right: 50; top: 0;">🔄</button>
        </div>
        <script>
        function togglePassword_{name}() {{
            const input = document.getElementById("id_{name}");
            if (input.type === "password") {{
                input.type = "text";
                setTimeout(() => {{
                    input.type = "password";
                }}, 3000);  // Auto-hide after 3 seconds
            }} else {{
                input.type = "password";
            }}
        }}
        function generatePassword_{name}() {{
            const input = document.getElementById("id_{name}");
            const length = 12;  // Length of the generated password
            const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+";
            const randomValues = new Uint32Array(length);
            crypto.getRandomValues(randomValues);
            let password = "";
            for (let i = 0; i < length; i++) {{
                password += charset[randomValues[i] % charset.length];
            }}
            input.value = password;
            input.type = "text";
            setTimeout(() => {{
                input.type = "password";
            }}, 3000);  // Auto-hide after 3 seconds
        }}
        </script>
    """

    def __init__(self, attrs=None, render_value=True):
        super().__init__(attrs=attrs, render_value=render_value)

    def render(self, name, value, attrs=None, renderer=None):
        # render_value=True keeps the stored plaintext SIP secret editable (with the
        # reveal toggle); escape it so a value containing " or < cannot break markup
        # or inject script.
        final_attrs = self.build_attrs(
            attrs, extra_attrs={"type": "password", "class": "vTextField"}
        )
        final_attrs_str = " ".join(
            f'{escape(k)}="{escape(v)}"' for k, v in final_attrs.items()
        )
        html = self.template.format(
            name=escape(name), value=escape(value or ""), attrs=final_attrs_str
        )
        return mark_safe(html)


class ChannelComboboxWidget(forms.TextInput):
    """Text input with a datalist of PJSIP channel suggestions (no extra JS deps)."""

    def __init__(self, choices=(), attrs=None):
        super().__init__(attrs)
        self.choices = list(choices)

    def render(self, name, value, attrs=None, renderer=None):
        datalist_id = f"datalist_{name}"
        extra = {"list": datalist_id}
        if attrs:
            attrs = {**attrs, **extra}
        else:
            attrs = extra
        input_html = super().render(name, value, attrs, renderer)
        options = "".join(f'<option value="{escape(ch)}">' for ch in self.choices)
        datalist_html = f'<datalist id="{datalist_id}">{options}</datalist>'
        return mark_safe(input_html + datalist_html)
