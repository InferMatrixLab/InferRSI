# Validation boundary

This directory is an import-scope declaration, **not** a newly frozen accelerator
validator. Original validators and gates remain in the source campaign identified
by task #35; they were not executed by this import or rewritten to fit it.

Repository checks validate schema, peer/source/backend/scenario filtering,
explicit unverified status, navigation and package-resource availability. Source
hashes describe fetched bytes, not inference correctness. New downstream
performance acceptance requires its own pre-search validator freeze and complete
L0–L4 evidence as defined by its acceptance issue.
