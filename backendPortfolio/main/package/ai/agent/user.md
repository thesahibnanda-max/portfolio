Surface: {{ surface.label }}

{% if context | trim %}
Context:
{{ context }}

{% endif %}
{% if history %}
Conversation so far:
{% for item in history %}
{{ item.role | upper }}: {{ item.content }}
{% endfor %}

{% endif %}
{% if style == "detailed" %}
Answer style: detailed -- cover the question thoroughly, up to about 300 words, still in plain terminal markdown.
{% elif style == "concise" %}
Answer style: concise -- lead with the answer, at most about 120 words.
{% endif %}
Current message:
{{ current_message }}
