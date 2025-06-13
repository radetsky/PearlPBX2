from django import forms
from django.utils.safestring import mark_safe


class PasswordWithToggleInput(forms.PasswordInput):
    template = '''
        <div style="position: relative;">
            <input type="password" name="{name}" value="{value}" id="id_{name}" {attrs}/>
            <button type="button" onclick="togglePassword_{name}()" style="position: absolute; right: 0; top: 0;">👁</button>
        </div>
        <script>
        function togglePassword_{name}() {{
            const input = document.getElementById("id_{name}");
            if (input.type === "password") {{
                input.type = "text";
            }} else {{
                input.type = "password";
            }}
        }}
        </script>
    '''

    def __init__(self, attrs=None, render_value=True):
        super().__init__(attrs=attrs, render_value=render_value)

    def render(self, name, value, attrs=None, renderer=None):
        final_attrs = self.build_attrs(
            attrs, extra_attrs={'type': 'password', 'class': 'vTextField'})
        final_attrs_str = ' '.join(
            [f'{k}="{v}"' for k, v in final_attrs.items()])
        html = self.template.format(
            name=name, value=value or '', attrs=final_attrs_str)
        return mark_safe(html)
