# Operator troubleshooting

| Failure | Diagnostic distinction | Correction |
|---|---|---|
| Invalid operator name during generation | Native schema version and YAML name/overload disagree | Use matching torchgen/torch release and exact overload before regeneration. |
| Undefined ACLNN symbol | Adapter/runtime feature mismatch | Confirm exact symbol availability and supported compatibility path; do not bypass validation to force launch. |
| Output values correct only for equal shapes | Example allocates like one input or derivative ignores broadcasting | Infer broadcast output shape; test both forward and gradient reduction. |
| Out tensor alias corrupts inputs | Mutation/overlap contract missing | Add overlap/shape/dtype validation and expected-error tests. |
| Forward succeeds but fake/compile fails | Meta shape/aliasing missing | Implement correct fake/Meta behavior, including symbolic dimensions. |
| Compiler succeeds but training gradient wrong | Device and autograd registrations are distinct | Validate derivative math and saved state independently. |
| Legacy ACL fallback is unexpectedly used | Runtime symbol check or config chooses compatibility implementation | Record chosen branch and compare it on actual target stack. |

Never claim inspecting op-plugin covers every operator, every CANN kernel, or
every hardware dtype. The readset covers a representative real adapter and the
generation/registration mechanisms.
