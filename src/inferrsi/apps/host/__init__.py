"""Apps host bindings: command probes, environment and device facts, and source
identity for this host.

``targets`` fingerprints source and ``platforms`` discovers and qualifies devices.
Device counts, SKUs and campaign settings are supplied by callers. Discovery does
not establish backend/model compatibility; qualification requires independent
evidence. The initializer imports nothing.
"""
