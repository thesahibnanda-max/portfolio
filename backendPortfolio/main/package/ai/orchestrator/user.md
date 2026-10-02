{% if history %}
Conversation so far:
{% for item in history %}
{{ item.role | upper }}: {{ item.content }}
{% endfor %}

{% endif %}
Current message:
{{ current_message }}
