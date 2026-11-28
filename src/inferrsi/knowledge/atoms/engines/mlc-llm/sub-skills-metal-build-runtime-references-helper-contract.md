# Apple target declaration helper

[audit_apple_target_declarations.py](../scripts/audit_apple_target_declarations.py)
provides audit(plan) and example(). It reproduces six selected source hint,
suffix, prefix and host-declaration rules, not TVM Target parsing, autodetection,
callback registration, compilation, ABI/link/load checks or GPU execution.

Input has exactly: schema_version integer 1; target_hint one of iphone,
iphone:generic, macabi, macabi:generic, metal:x86-64, metal:generic; output_suffix
a dot plus 1–16 ASCII alphanumeric/underscore chars (not a path); host_hint auto
or a bounded opaque triple; prefix_hint auto, empty or a bounded identifier;
model_name/quantization opaque 1–80-char alphanumeric/underscore/hyphen names;
macabi_arch null or a string of at most 64 chars. No actual environment is read.
The helper's narrow grammar is not a complete upstream argument validator.

Output reports the source builder, static/shared declaration, SDK/export arch
where the selected builder supplies one, preset host versus separately unresolved
host hint, literal resolved prefix, conflicts and source warnings. Example
iphone:generic/.tar/auto gives SDK iphoneos, preset arm64-apple-darwin and prefix
demo_model_q4f16_1_. Explicit prefix plus the colon hint instead yields empty
and a source warning. Missing static prefix is not a build rejection. Invalid
macabi architecture falls back to arm64; its Metal SDK remains macosx.

For generic Metal, the source default builder does not supply the special
x86-64/iPhone SDK callback: null SDK means not established by this selected
builder, not proof that no compiler callback exists elsewhere. Auto host stays
unresolved. Export architecture is not a resolved host target.

--example prints synthetic input; file/stdin prints analysis. Supported valid
declarations return 0; an inspected builder's required suffix conflict returns
1; malformed input returns 2 with fixed diagnostics. Input is capped at 16 KiB,
finite UTF-8 JSON without duplicate keys. Wrong types/booleans, extra/missing
fields, overly deep/oversized JSON and known nonregular files are rejected.
The regular-file precheck is not an atomic hostile-filesystem guard.

Every result keeps compiler/native not_run, actual artifact ABI/exports/format
not_inspected and SDK/runtime/fit not_verified. The helper does not inspect an
artifact's runnable property, kernel bytes or exports. Only stdout/stderr is
written, with no subprocess, network, SDK/device or source imports.
