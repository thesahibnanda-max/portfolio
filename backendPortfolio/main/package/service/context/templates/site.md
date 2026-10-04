SITE:
{{ owner_name }}'s portfolio has two ways to talk to its AI: the chat panel on the home page ("Ask my AI", ⌘K) and the Portfolio Agent CLI, a terminal at /cli opened from the chat panel or the ">_" link in the navigation. Both share one history of conversations, and conversations started in the terminal are tagged "cli".
In the terminal, "skills" means its slash commands, not {{ owner_name }}'s technical skills. It has {{ skills | length }} skills in {{ plugins | length }} plugins; {{ default_count }} skills are available by default.
{% for plugin in plugins %}
Plugin "{{ plugin.name }}" ({{ "always on" if not plugin.removable else ("on by default" if plugin.enabled_by_default else "off by default") }}, {{ counts[plugin.name] }} skill{{ "" if counts[plugin.name] == 1 else "s" }}): {{ plugin.summary }}
{% for skill in skills if skill.plugin == plugin.name %}
- {{ skill.usage }}: {{ skill.summary }}{% if skill.aliases %} (aliases: {{ skill.aliases | map("format_alias") | join(", ") }}){% endif %}

{% endfor %}
{% endfor %}
Plugins are managed with /plugins (for example "/plugins enable extras"); the "core" plugin cannot be turned off.
Settings (/config, or "/config <key> <value>"):
{% for setting in settings %}
- {{ setting.key }} ({{ setting.label }}): {{ setting.options | join(" | ") }}, default {{ setting.default }}. {{ setting.summary }}
{% endfor %}
Modes (Shift+Tab cycles them): default answers a question directly; auto-run makes a short plan of terminal commands and runs it; plan mode shows that plan and waits for Enter.
Keys: Tab or → completes, ↑↓ recall earlier input, Esc or Ctrl+C stops an answer, Ctrl+L clears the screen, Shift+Tab changes the mode.
Slash commands run in the browser and cost no AI calls; only questions to the agent use the AI, at most one call each, and repeated questions are answered from a cache.
