PROFILE:
Name: {{ profile.profile_details.name }}
Email: {{ profile.profile_details.email }}
{% if leetcode.country_name %}
Country: {{ leetcode.country_name }}
{% endif %}
{% if leetcode.linkedin_url %}
LinkedIn: {{ leetcode.linkedin_url }}
{% endif %}
{% if leetcode.twitter_url %}
Twitter: {{ leetcode.twitter_url }}
{% endif %}
{% if leetcode.websites %}
Websites: {{ leetcode.websites | join(", ") }}
{% endif %}
{% if profile.languages %}
Languages spoken: {{ profile.languages | join(", ") }}
{% endif %}
GitHub usernames: {{ github_usernames | join(", ") }}
LeetCode usernames: {{ leetcode_usernames | join(", ") }}
Codeforces usernames: {{ codeforces_usernames | join(", ") }}
{% if profile.skills_by_category %}
Skills:
{% for category, skills in profile.skills_by_category.items() %}
- {{ category }}: {{ skills | join(", ") }}
{% endfor %}
{% endif %}
{% if profile.achievements %}
Achievements: {{ profile.achievements | join(", ") }}
{% endif %}
{% if profile.experience %}
Experience:
{% for job in profile.experience %}
- {{ job.title }} at {{ job.company }}, {{ job.location }}, {{ job.employment_type }} ({{ job.start_date }} to {{ job.end_date }}): {{ job.description | join(" ") }} [{{ job.technologies | join(", ") }}]
{% endfor %}
{% endif %}
{% if profile.education %}
Education:
{% for school in profile.education %}
- {{ school.degree }}, {{ school.field }}, {{ school.institution }} ({{ school.start_date }} to {{ school.end_date }}), Grade: {{ school.grade }}
{% endfor %}
{% endif %}
{% if profile.projects %}
Projects:
{% for project in profile.projects %}
- {{ project.name }} ({{ project.year }}, {{ project.link }}): {{ project.description | join(" ") }} [{{ project.technologies | join(", ") }}]
{% endfor %}
{% endif %}
