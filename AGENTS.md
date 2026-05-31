# How to delegate
Use the "delegate" subagent to perform tasks. This keeps your context clear and concise.
Call subagents sequentially, never call them in parallel.
Give one precise task per subagent, do not overwhelm them with multiple tasks.

# How to explore the codebase
First, as previously noted, you should be using a "delegate" subagent, even to explore the codebase. This subagent can give you a report, make sure to ask it precisely for what you want.
Next, for the subagent, when listing files, especially when using recursive listing, make sure to ignore "node_modules", ".venv" and the "cache" directory unless you need to see their contents.

# Code quality
Explicitly type your code.
Write or update existing tests. Unit tests should not be exhaustive, but instead cover the expected behaviors as well as the edge cases.

# User interactions
Ask question to the user if unclear.
The user prompt may override any of the above, these are not absolute rules.
