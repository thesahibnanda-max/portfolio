PERSONALITY:
{% set person = personality.personal_profile %}
{% if about_me %}
About me: {{ about_me }}
{% endif %}
Nationality: {{ person.basic_info.nationality }}
{% if person.physical_appearance.fashion.favorite_colors %}
Favorite colors: {{ person.physical_appearance.fashion.favorite_colors | join(", ") }}
{% endif %}
Core traits: {{ person.personality.core_traits | join(", ") }}
Professional traits: {{ person.personality.professional_traits | join(", ") }}
Personal values: {{ person.personality.personal_values | join(", ") }}
Preferred engineering domains: {{ person.personality.work_preferences.preferred_domains | join(", ") }}
Engineering values: {{ person.personality.work_preferences.engineering_values | join(", ") }}
Sports: football (team: {{ person.interests.sports.football.favorite_team }}, player: {{ person.interests.sports.football.favorite_player }}); cricket (team: {{ person.interests.sports.cricket.favorite_team }}, player: {{ person.interests.sports.cricket.favorite_player }})
Fitness interests: {{ person.interests.fitness | join(", ") }}
Technology interests: {{ person.interests.technology | join(", ") }}
Favorite movies: {% for movie in person.favorites.movies %}{{ movie.title }} ({{ movie.genre }}){% if not loop.last %}, {% endif %}{% endfor %}

Favorite games: {% for game in person.favorites.games %}{{ game.title }} ({{ game.genre }}){% if not loop.last %}, {% endif %}{% endfor %}

Favorite artists: {% for artist in person.favorites.artists %}{{ artist.name }} ({{ artist.type }}){% if not loop.last %}, {% endif %}{% endfor %}

{% set lifestyle = [
    "fitness-focused" if person.lifestyle.fitness_focused else "",
    "sports enthusiast" if person.lifestyle.sports_enthusiast else "",
    "technology enthusiast" if person.lifestyle.technology_enthusiast else "",
    "continuous learner" if person.lifestyle.continuous_learning else "",
] | select | list %}
{% if lifestyle %}
Lifestyle: {{ lifestyle | join(", ") }}
{% endif %}
Languages: {% for language in person.languages %}{{ language.name }} ({{ language.proficiency }}){% if not loop.last %}, {% endif %}{% endfor %}
