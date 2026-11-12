# Apps output publication

The Apps output slice remains a proposed contract under #371. This document
records implementation limits, not design acceptance or production readiness.

## Atomicity and platform support

Publication requires staging and destination on the same filesystem. Linux uses
libc `renameat2(RENAME_NOREPLACE)`, macOS uses `renamex_np(RENAME_EXCL)`, and
Windows uses Python's no-replacement directory rename. Every destination entry,
including an empty directory, is a conflict. There is no check-then-rename or
copy fallback that could overwrite another publisher's output.

Linux requires a libc exposing renameat2 and a filesystem/kernel combination
supporting RENAME_NOREPLACE. POSIX also requires working directory fsync. Other
POSIX platforms, missing APIs, and filesystems rejecting these operations fail
closed. Local Linux filesystems and local Windows NTFS are the intended targets;
this does not certify every filesystem with that name. NFS, FUSE, WSL drvfs,
macOS and other remote/removable filesystems need environment-specific validation
before any support or crash-durability claim. No network filesystem is implicitly
supported by the Python API.

## Durability and failure reporting

Both JSON files are flushed and fsynced before publication. POSIX additionally
syncs the workspace (which may have gained the output root), the staging directory
and output root before the no-replace rename, then syncs the output root after it.
Atomic visibility and power-loss durability are different properties. Windows
has no portable directory-fsync equivalent here: the implementation guarantees
no-replacement publication on supported local filesystems, not power-loss
persistence of the renamed directory. Storage hardware and mount guarantees
still apply even when POSIX fsync succeeds.

Failures retain ArchivePersistenceError and exit code 6, with safe messages
separating destination conflict, unsupported atomic rename/directory sync,
validation failure, and other I/O failures. Raw paths and arbitrary exception
messages are not included. An EINVAL from the atomic operation or directory sync
is classified as unsupported rather than as a destination conflict.

If rename succeeded but the final sync failed, the output may be visible. The
return explicitly reports uncertain publication durability, preserves underlying
committed references, and does not remove or overwrite that directory. Inspect
the same output ID and its manifest before considering a retry; directory=None
means the call did not confirm success, not proof that no directory exists.

## Port response validation and references

Malformed binder or Harness return values become a validation-stage
InvalidExecutionSpec result with exit code 2. Raised typed PublicError is handled
as a port error. Other host exceptions remain exceptions: these are programming
or host failures, not automatically trustworthy core responses. The future CLI
must define its own exception presentation; no CLI behavior is implied here.

Non-null error attempt IDs, latest record references and partial execution
identities must belong to the submitted attempt. Partial facts are type checked.
Unknown or invalid values are not invented to make a response pass validation.
Retained artifact references receive metadata validation only. Apps does not
follow arbitrary locators or perform implicit storage I/O while projecting an
error. A consumer must use an authorized storage reader and verify the bytes,
size and digest before treating a referenced artifact as evidence. Validating
the result.json digest does not validate all referenced artifacts.

The pure Harness execution_spec module owns request_digest, while run_store
retains a compatibility import. This avoids making Apps depend on the storage
implementation merely to compute the canonical digest. This proposed public
surface remains subject to Harness owner and maintainer acceptance.
