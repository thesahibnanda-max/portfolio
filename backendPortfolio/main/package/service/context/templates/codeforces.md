{% for account in accounts %}
CODEFORCES ({{ account.details.handle }}):{% if account.details.current_rating is not none %} current rating {{ account.details.current_rating }},{% endif %}{% if account.details.max_rating is not none %} max rating {{ account.details.max_rating }},{% endif %} {{ account.details.contests_count }} rated contests
{% if account.recent_changes %}
Recent contests: {% for change in account.recent_changes %}{{ change.contest_name }} (rank {{ change.rank }}): {{ change.old_rating }}->{{ change.new_rating }}{% if not loop.last %}; {% endif %}{% endfor %}

{% endif %}
{% endfor %}
