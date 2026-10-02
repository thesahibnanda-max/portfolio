{% for details in accounts %}
LEETCODE ({{ details.username }}):{% if details.ranking is not none %} rank {{ details.ranking }},{% endif %}{% if details.total_solved is not none %} {{ details.total_solved }} solved ({{ details.easy_solved }} easy, {{ details.medium_solved }} medium, {{ details.hard_solved }} hard){% endif %}{% if details.contest_rating is not none %}, contest rating {{ details.contest_rating }}{% endif %}{% if details.current_streak is not none %}, current streak {{ details.current_streak }} days{% endif %}

{% if details.badges %}
Badges: {{ details.badges | join(", ") }}
{% endif %}
{% if details.language_problems_solved %}
Languages used: {% for language, solved in details.language_problems_solved.items() %}{{ language }} {{ solved }}{% if not loop.last %}, {% endif %}{% endfor %}

{% endif %}
{% endfor %}
