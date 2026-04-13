from django.db import migrations


MACRO_TEXT = """
COUNTRY_CODE = "380";
COUNTRY_CODE_LEN = 3;
IDD_PREFIX = "00";
IDD_PREFIX_LEN = 2;
LOCAL_CODE = "044";
PADDING_LEFT = "0";
REQUIRED_LEN = 10;
CITYCODE_LEN = 7;

if ("${CALLERID(num)}" == "Anonymous") {
    return;
}
if ("${CALLERID(num)}" == "evakuator") {
    Set(CALLERID(num)=${CALLERID(name)});
}

caller_id = ${FILTER(0-9,${CALLERID(num)})};

caller_id_len = ${LEN(${caller_id})};

if (${caller_id_len} == ${REQUIRED_LEN}) {
    Set(CALLERID(num)=${caller_id});
    return;
}

if (${caller_id_len} > ${REQUIRED_LEN}) {
    prefix_num = ${caller_id:0:${COUNTRY_CODE_LEN}};
    if ("${prefix_num}" == "${COUNTRY_CODE}") {
        prefix_len = ${caller_id_len} - ${REQUIRED_LEN};
        caller_id = ${caller_id:${prefix_len}};
        Set(CALLERID(num)=${caller_id});
        return;
    }
    idd_cc_len = ${MATH(${IDD_PREFIX_LEN}+${COUNTRY_CODE_LEN},i)};
    prefix_idd = ${caller_id:0:${idd_cc_len}};
    idd_country_code = ${IDD_PREFIX}${COUNTRY_CODE};
    if ("${prefix_idd}" == "${idd_country_code}") {
        prefix_len = ${caller_id_len} - ${REQUIRED_LEN};
        caller_id = ${caller_id:${prefix_len}};
        Set(CALLERID(num)=${caller_id});
        return;
    }
}

if (${caller_id_len} < ${REQUIRED_LEN}) {
    if (${caller_id_len} == ${CITYCODE_LEN}) {
        Set(CALLERID(num)=${LOCAL_CODE}${caller_id});
        return;
    }
    if (${caller_id_len} == ${REQUIRED_LEN} - 1) {
        Set(CALLERID(num)=${PADDING_LEFT}${caller_id});
        return;
    }
}

Set(CALLERID(num)=${caller_id});
return;
"""


def update_macro(apps, schema_editor):
    DialplanMacro = apps.get_model("core", "DialplanMacro")
    DialplanMacro.objects.filter(name="callerid_normalization").update(
        macro=MACRO_TEXT,
        description="Normalize CallerID to Ukrainian/Kyiv format",
    )


def revert_macro(apps, schema_editor):
    DialplanMacro = apps.get_model("core", "DialplanMacro")
    DialplanMacro.objects.filter(name="callerid_normalization").update(
        macro="""
COUNTRY_CODE = "380";
COUNTRY_CODE_LEN = 3;
LOCAL_CODE = "044";
PADDING_LEFT = "0";
REQUIRED_LEN = 10;
CITYCODE_LEN = 7;

if ("${CALLERID(num)}" == "Anonymous"){
        return;
}
caller_id = ${CALLERID(num)};
first_character = ${caller_id:0:1};
if ("${first_character}" == "+") {
    caller_id = ${caller_id:1};
}

caller_id_len = ${LEN(${caller_id})};
if (${caller_id_len} == ${REQUIRED_LEN}) {
    Set(CALLERID(num)=${caller_id});
    return;
}

if (${caller_id_len} > ${REQUIRED_LEN}) {
    prefix_num = ${caller_id:0:${COUNTRY_CODE_LEN}};
    if (${prefix_num} == ${COUNTRY_CODE}) {
        prefix_len = ${LEN(${caller_id})} - ${REQUIRED_LEN};
        caller_id  = ${caller_id:${prefix_len}};
        Set(CALLERID(num)=${caller_id});
        return;
    }
}

if (${LEN(${caller_id})} < ${REQUIRED_LEN}) {
    if (${caller_id_len} == ${CITYCODE_LEN}) {
        Set(CALLERID(num)=${LOCAL_CODE}${caller_id});
        return;
    }
    if (${caller_id_len} == ${REQUIRED_LEN}-1) {
        Set(CALLERID(num)="${PADDING_LEFT}${caller_id}");
        return;
    }
}

Set(CALLERID(num)=${caller_id});
return;
""",
        description="Normalize CallerID to Ukrainian/Kyiv format",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0065_alter_managerusers_writetimeout"),
    ]

    operations = [
        migrations.RunPython(update_macro, revert_macro),
    ]
