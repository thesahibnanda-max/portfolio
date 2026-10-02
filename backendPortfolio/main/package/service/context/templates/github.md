{% for account in accounts %}
GITHUB ({{ account.details.username }}):{% if account.details.public_repos is not none %} {{ account.details.public_repos }} public repos,{% endif %}{% if account.details.followers is not none %} {{ account.details.followers }} followers,{% endif %}{% if account.details.following is not none %} {{ account.details.following }} following.{% endif %}{% if account.details.bio %} Bio: {{ account.details.bio }}{% endif %}

{% if account.top_repositories %}
Top repos: {% for repository in account.top_repositories %}{{ repository.name }}{% if repository.language %} ({{ repository.language }}){% endif %} - {{ repository.stars or 0 }} stars{% if repository.description %}: {{ repository.description }}{% endif %}{% if not loop.last %}; {% endif %}{% endfor %}

{% endif %}
{% endfor %}
