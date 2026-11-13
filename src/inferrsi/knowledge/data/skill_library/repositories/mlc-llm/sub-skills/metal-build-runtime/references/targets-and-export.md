# Apple presets, host, SDK and exported identity

Pinned [auto_target.py](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/support/auto_target.py)
owns the following source declarations. They are not measured device limits or
proof that a compiler/SDK exists.

| Hint | Source route | Export/host/SDK distinction |
| --- | --- | --- |
| iphone / iphone:generic | Metal preset, iPhone builder | Static .tar, system_lib true; host arm64-apple-darwin; callback uses iphoneos SDK |
| macabi / macabi:generic | Metal preset, same iPhone builder | Static .tar; host arm64 or x86_64-apple-ios18.0-macabi; Metal SDK is macosx, not iphoneos |
| metal:x86-64 | x86-64 Metal builder | Requires .dylib, export sdk macosx/arch x86_64; host target is filled separately when absent |
| metal:generic | Default builder | .tar/.lib are system libraries; .so/.dylib/.dll shared; unknown suffix warns and assumes shared; host remains separate |

Bare iphone/macabi normalize to :generic for GPU target detection. Existing
preset hosts are not overwritten by a host hint; otherwise host detection is a
separate step. Source MLC_MACABI_ARCH strips whitespace, accepts arm64/x86_64
and falls back to arm64 for absent/empty/invalid strings. A host triple,
export architecture and SDK argument describe different parts of the build.
The helper records declarations without invoking detection or parsing TVM targets.

The iPhone builder registers a process-global tvm_callback_metal_compile override.
It passes the target's first libs entry as SDK when present; without libs it
calls the dependency compiler without an explicit SDK. This is not an immutable
per-artifact callback/SDK setting. Record the actual matched callback/toolchain
before comparing artifacts. The external xcode helper is a separate dependency
contract, not audited by a source string screener.

## Preserve literal prefix behavior

[detect_system_lib_prefix](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/support/auto_target.py#L384-L413)
uses startswith iphone/macabi/android for auto prefixes, deriving
model_name_quantization_ and replacing hyphens with underscores. That identity
must agree with the packaged tar/model_lib; renaming an archive without
reconciling it is not a harmless filesystem change.

Non-auto explicit prefixes are returned only for **bare** iphone/macabi/android
hints. Thus explicit prefix plus iphone:generic or macabi:generic returns empty
at this pin. Do not silently repair this behavior in a distillation. Other
Metal hints also return empty from this detector. Direct lower-level builder
arguments are a different call path and must be recorded as such.

The builder applies a nonempty prefix as an IR attribute only for system/static
libraries. Missing static prefix warns rather than rejecting; a supplied shared
prefix warns and has no attribute effect. The helper models the selected prefix
detector followed by builder classification, not every direct builder call or
platform linking rule. Preset thread/shared-memory constants are source inputs,
not universal tuning or acceptance thresholds.
