New message from your portfolio's contact form.

From: {{ email }}
Subject: {{ subject }}
Sent: {{ submitted_at }}
{% if client_ip is not none %}
IP: {{ client_ip }}
{% endif %}

----------------------------------------

{{ message }}

----------------------------------------
Reply to this mail to answer {{ email }} directly.
