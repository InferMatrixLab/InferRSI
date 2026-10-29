# Dsp Library Packaging

## User Persona
Maintainer or operator debugging a concrete Local Dream boundary.

## Scenario Coverage
Source-informed packaging advanced case; prompt in `user_request.txt`. Expected owner files are in `assertions.json`. No original upstream test spans this scenario, so this is synthetic.

## Expected Successful Behavior
- Separate CPU DiT shared library from DSP skels staged in assets.
- Distinguish dlopen, entry, ABI negotiation, create and actual device work.
- Retain native block and separate SDK/gitlink/patch identities.

## Failure Signals
Generic advice without the specified source distinction, source-checkout runtime dependence, copied private paths, unsafe host exposure, license erasure or synthetic/native evidence conflation.
