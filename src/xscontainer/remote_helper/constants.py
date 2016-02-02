MONITOR_EVENTS_POLL_INTERVAL = 1
# The heavy weight is docker ps with plenty of containers.
# Assume 283 bytes per container.
# 300KB should be enough for 1085 containers.
MAX_BUFFER_SIZE = 300 * 1024
