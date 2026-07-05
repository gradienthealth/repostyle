# Changelog

## [0.12.0](https://github.com/gradienthealth/repostyle/compare/repostyle-v0.11.0...repostyle-v0.12.0) (2026-07-05)


### Features

* **NO-ISSUE:** add RS033 to flag non-conforming filenames ([#77](https://github.com/gradienthealth/repostyle/issues/77)) ([4330df1](https://github.com/gradienthealth/repostyle/commit/4330df1cca513c6b84e696fab7a1ea12593b8644))

## [0.11.0](https://github.com/gradienthealth/repostyle/compare/repostyle-v0.10.1...repostyle-v0.11.0) (2026-07-04)


### Features

* **NO-ISSUE:** add RS032 to flag a return value narrated in docstring prose ([#74](https://github.com/gradienthealth/repostyle/issues/74)) ([48b1dbb](https://github.com/gradienthealth/repostyle/commit/48b1dbbead93e9ad9a934c1ae427b45db44a2b3c))


### Bug Fixes

* **NO-ISSUE:** recurse into directory arguments instead of silently linting nothing ([#72](https://github.com/gradienthealth/repostyle/issues/72)) ([96f398e](https://github.com/gradienthealth/repostyle/commit/96f398eea1a535f91806a32dbc9cd56600cef221))

## [0.10.1](https://github.com/gradienthealth/repostyle/compare/repostyle-v0.10.0...repostyle-v0.10.1) (2026-07-03)


### Bug Fixes

* **NO-ISSUE:** bump the gate pins to current versions ([#70](https://github.com/gradienthealth/repostyle/issues/70)) ([9b8a7cf](https://github.com/gradienthealth/repostyle/commit/9b8a7cf86baf00472df5f9dca812c5fb4d425dc9))

## [0.10.0](https://github.com/gradienthealth/repostyle/compare/repostyle-v0.9.0...repostyle-v0.10.0) (2026-07-03)


### Features

* **NO-ISSUE:** add a gates extra for package-route consumption ([#68](https://github.com/gradienthealth/repostyle/issues/68)) ([b52f8e8](https://github.com/gradienthealth/repostyle/commit/b52f8e886411896143550d2a856c406d6891d144))

## [0.9.0](https://github.com/gradienthealth/repostyle/compare/repostyle-v0.8.0...repostyle-v0.9.0) (2026-07-03)


### Features

* **NO-ISSUE:** export the house lint gate suite as repostyle hooks ([#67](https://github.com/gradienthealth/repostyle/issues/67)) ([d8cf149](https://github.com/gradienthealth/repostyle/commit/d8cf14955434fb704617495c5680f030727fec17))
* **PROC-2381:** extend RS022 to TOML and YAML comments ([#65](https://github.com/gradienthealth/repostyle/issues/65)) ([c3ba78b](https://github.com/gradienthealth/repostyle/commit/c3ba78bcadc742bc08eb8ce24dc38e3264b63117))

## [0.8.0](https://github.com/gradienthealth/repostyle/compare/repostyle-v0.7.0...repostyle-v0.8.0) (2026-06-30)


### Features

* **PROC-2383:** relax prose fill to 79 and reflow TOML/YAML in --fix ([#64](https://github.com/gradienthealth/repostyle/issues/64)) ([86801ad](https://github.com/gradienthealth/repostyle/commit/86801ad7beafc36afe406173d340ae9cb6e342f5))


### Bug Fixes

* **PROC-2383:** keep ruff max-doc-length at 88 ([#61](https://github.com/gradienthealth/repostyle/issues/61)) ([6f64d99](https://github.com/gradienthealth/repostyle/commit/6f64d993f1e2ff99530ab48b737c1b730cb3c133))
* **PROC-2383:** set ruff max-doc-length to 72 ([#63](https://github.com/gradienthealth/repostyle/issues/63)) ([730963b](https://github.com/gradienthealth/repostyle/commit/730963b7be7c4d74f97d27dac6aae9a8eb0bc20e))

## [0.7.0](https://github.com/gradienthealth/repostyle/compare/repostyle-v0.6.0...repostyle-v0.7.0) (2026-06-30)


### ⚠ BREAKING CHANGES

* **PROC-2383:** package, console script, pre-commit hook id, config table (`[tool.pystyle]` → `[tool.repostyle]`), and release tag prefix are renamed from pystyle to repostyle; consumers must update their pins and table. The hook lints TOML/YAML comments by default, so unwrapped config comments newly fail RS009.
* **NO-ISSUE:** rename the package and module from gradient-pystyle to pystyle ([#25](https://github.com/gradienthealth/repostyle/issues/25))

### Features

* **NO-ISSUE:** add RS025 rejecting make_ outside test modules ([#30](https://github.com/gradienthealth/repostyle/issues/30)) ([7707a30](https://github.com/gradienthealth/repostyle/commit/7707a30f37f79e4e726932cf52109cc95bf5080c))
* **NO-ISSUE:** rename the package and module from gradient-pystyle to pystyle ([#25](https://github.com/gradienthealth/repostyle/issues/25)) ([909c7ef](https://github.com/gradienthealth/repostyle/commit/909c7efced3ccd26acba0d83ba5442ee86b8c085))
* **PROC-2277:** emit column offsets from gradient-pystyle violations ([e399129](https://github.com/gradienthealth/repostyle/commit/e3991294cd58ff45e9636e8c253445aeada81361))
* **PROC-2278:** add per-line and per-file suppression comments ([ba2b007](https://github.com/gradienthealth/repostyle/commit/ba2b0072bb82189e95a92fa32698e63665391ced))
* **PROC-2279:** extend --fix to the RS005 and RS030 prose rules ([#56](https://github.com/gradienthealth/repostyle/issues/56)) ([3604b6b](https://github.com/gradienthealth/repostyle/commit/3604b6b52318fde5182f1a8c2eac23cde88e3d6c))
* **PROC-2280:** add structure-aware RS009 reflow with --fix autofix ([#20](https://github.com/gradienthealth/repostyle/issues/20)) ([1c642e4](https://github.com/gradienthealth/repostyle/commit/1c642e40ea74e4c25f886e75e4a76f16b9845357))
* **PROC-2281:** add RS031 and drop RS018's parameter-count Args trigger ([#46](https://github.com/gradienthealth/repostyle/issues/46)) ([987dbba](https://github.com/gradienthealth/repostyle/commit/987dbbab39ff3c0537b3598f1e9c0238dda9fbb0))
* **PROC-2282:** enable Ruff D401 imperative-mood in the baseline ([43a89b7](https://github.com/gradienthealth/repostyle/commit/43a89b75772bb6e17d236a2fe6f33e4ad2d5ff85))
* **PROC-2301:** add complexity and size guardrails to ruff-base ([#5](https://github.com/gradienthealth/repostyle/issues/5)) ([d70c8d6](https://github.com/gradienthealth/repostyle/commit/d70c8d626026e469fa6b96fe7d946cdd8b4e53e4))
* **PROC-2302:** add cognitive-complexity and test-quality rules ([d04dc74](https://github.com/gradienthealth/repostyle/commit/d04dc746b36eaaefcb907fa67afaad1a96e392e7))
* **PROC-2303:** add the RS018 documentation-value signal ([2e8130a](https://github.com/gradienthealth/repostyle/commit/2e8130ab21781ebc4e01177284dc98c73efbf249))
* **PROC-2304:** scope lint enforcement to a PR's changed lines ([31427cb](https://github.com/gradienthealth/repostyle/commit/31427cb1eaee41878b83da174285580ba7467dfa))
* **PROC-2305:** add warn/error severity levels to gradient-pystyle rules ([439ec9c](https://github.com/gradienthealth/repostyle/commit/439ec9c829141ab38c18ea427db8fd3fa8f7904d))
* **PROC-2316:** add config-driven banned-import-by-path rule ([f24e957](https://github.com/gradienthealth/repostyle/commit/f24e9575513c7a18eb266c47d90d0b6114c2f193))
* **PROC-2318:** ban in-function imports in the shared ruff baseline ([#35](https://github.com/gradienthealth/repostyle/issues/35)) ([4bde651](https://github.com/gradienthealth/repostyle/commit/4bde65136b1d2fe281263f925fcce1befcc3047f))
* **PROC-2319:** add the RS027 too-many-positional-arguments rule ([#36](https://github.com/gradienthealth/repostyle/issues/36)) ([e3232e6](https://github.com/gradienthealth/repostyle/commit/e3232e6f1b29381b9ba74400eba23daa6b03a5ac))
* **PROC-2320:** add a module and class element-ordering rule ([#22](https://github.com/gradienthealth/repostyle/issues/22)) ([cbfc170](https://github.com/gradienthealth/repostyle/commit/cbfc1704a0fc7633f2a21a7239162a0df5962e0d))
* **PROC-2323:** add the RS029 should-be-private visibility rule ([#40](https://github.com/gradienthealth/repostyle/issues/40)) ([49bc7a3](https://github.com/gradienthealth/repostyle/commit/49bc7a3470675e07c967957a2aac206b5850bf69))
* **PROC-2325:** add agent-facing rule explanations via an explain subcommand ([#48](https://github.com/gradienthealth/repostyle/issues/48)) ([46217c3](https://github.com/gradienthealth/repostyle/commit/46217c3cbee99982ecf78f974777fcb3e19b306e))
* **PROC-2338:** add documentation-form rules for comment-vs-docstring placement ([#24](https://github.com/gradienthealth/repostyle/issues/24)) ([4117a71](https://github.com/gradienthealth/repostyle/commit/4117a71847139fc627cf576ce2ec3a84cb27fe4d))
* **PROC-2339:** add a comment-tag format rule for special comments ([#23](https://github.com/gradienthealth/repostyle/issues/23)) ([bd91110](https://github.com/gradienthealth/repostyle/commit/bd91110b6ef8904ee5d7466bfe0faf1fe67f836a))
* **PROC-2340:** add boolean-naming rules for prefix and embedded negation ([#29](https://github.com/gradienthealth/repostyle/issues/29)) ([87a3b19](https://github.com/gradienthealth/repostyle/commit/87a3b190aac2a082e06d6c6464504a36fc6aacb1))
* **PROC-2352:** add the RS028 exception-alias naming rule ([#33](https://github.com/gradienthealth/repostyle/issues/33)) ([aaab33a](https://github.com/gradienthealth/repostyle/commit/aaab33aac4fc72f4db58de9e707dbe33e7411f9e))
* **PROC-2356:** treat backticked references as atomic tokens when reflowing docstrings ([#37](https://github.com/gradienthealth/repostyle/issues/37)) ([42b42ad](https://github.com/gradienthealth/repostyle/commit/42b42ad4c496c6615af73d0dc1f8eb4bc92b9cc3))
* **PROC-2371:** add the RS030 terminal-punctuation rule for docstrings and comments ([#47](https://github.com/gradienthealth/repostyle/issues/47)) ([9270532](https://github.com/gradienthealth/repostyle/commit/927053203d0d9285021cc43bad5e91c0208e8f71))
* **PROC-2376:** enable Ruff FBT and ANN401 in the shared baseline ([#51](https://github.com/gradienthealth/repostyle/issues/51)) ([e89dc17](https://github.com/gradienthealth/repostyle/commit/e89dc17aed654bf6869ec07c5a28fd7b31a7b9fe))
* **PROC-2383:** rename to repostyle and add cross-language comment checks ([#58](https://github.com/gradienthealth/repostyle/issues/58)) ([e436d0d](https://github.com/gradienthealth/repostyle/commit/e436d0d95ae2284aa29cf06bc3eed85835959d42))


### Bug Fixes

* **NO-ISSUE:** exempt a literal sleep(0) from RS014's flaky-sleep check ([#45](https://github.com/gradienthealth/repostyle/issues/45)) ([e539aea](https://github.com/gradienthealth/repostyle/commit/e539aea5bc2d5c42951fdf24effd5d725a9d6442))
* **PROC-2356:** leave a backtick span wrapped across source lines untouched ([#38](https://github.com/gradienthealth/repostyle/issues/38)) ([7447019](https://github.com/gradienthealth/repostyle/commit/7447019679c6a6046af21772383bcf7954054876))
* **PROC-2375:** count a class body as definition-time for RS019 ordering ([#49](https://github.com/gradienthealth/repostyle/issues/49)) ([f701561](https://github.com/gradienthealth/repostyle/commit/f7015617cc50f029b07b5e594daff76a45540c23))


### Documentation

* **NO-ISSUE:** add the judgment-conventions canon ([#31](https://github.com/gradienthealth/repostyle/issues/31)) ([fa99759](https://github.com/gradienthealth/repostyle/commit/fa99759b5f599a75bcce56a58a97b22e2a8d092b))
* **NO-ISSUE:** note RS026 graduation in the boolean convention ([#53](https://github.com/gradienthealth/repostyle/issues/53)) ([03a46ed](https://github.com/gradienthealth/repostyle/commit/03a46ed0f5b20937dbdd5185ce4e7953da18c401))

## [0.6.0](https://github.com/gradienthealth/pystyle/compare/pystyle-v0.5.0...pystyle-v0.6.0) (2026-06-28)


### Features

* **PROC-2376:** enable Ruff FBT and ANN401 in the shared baseline ([#51](https://github.com/gradienthealth/pystyle/issues/51)) ([e89dc17](https://github.com/gradienthealth/pystyle/commit/e89dc17aed654bf6869ec07c5a28fd7b31a7b9fe))


### Documentation

* **NO-ISSUE:** note RS026 graduation in the boolean convention ([#53](https://github.com/gradienthealth/pystyle/issues/53)) ([03a46ed](https://github.com/gradienthealth/pystyle/commit/03a46ed0f5b20937dbdd5185ce4e7953da18c401))

## [0.5.0](https://github.com/gradienthealth/pystyle/compare/pystyle-v0.4.0...pystyle-v0.5.0) (2026-06-27)


### Features

* **PROC-2281:** add RS031 and drop RS018's parameter-count Args trigger ([#46](https://github.com/gradienthealth/pystyle/issues/46)) ([987dbba](https://github.com/gradienthealth/pystyle/commit/987dbbab39ff3c0537b3598f1e9c0238dda9fbb0))
* **PROC-2323:** add the RS029 should-be-private visibility rule ([#40](https://github.com/gradienthealth/pystyle/issues/40)) ([49bc7a3](https://github.com/gradienthealth/pystyle/commit/49bc7a3470675e07c967957a2aac206b5850bf69))
* **PROC-2325:** add agent-facing rule explanations via an explain subcommand ([#48](https://github.com/gradienthealth/pystyle/issues/48)) ([46217c3](https://github.com/gradienthealth/pystyle/commit/46217c3cbee99982ecf78f974777fcb3e19b306e))
* **PROC-2371:** add the RS030 terminal-punctuation rule for docstrings and comments ([#47](https://github.com/gradienthealth/pystyle/issues/47)) ([9270532](https://github.com/gradienthealth/pystyle/commit/927053203d0d9285021cc43bad5e91c0208e8f71))


### Bug Fixes

* **NO-ISSUE:** exempt a literal sleep(0) from RS014's flaky-sleep check ([#45](https://github.com/gradienthealth/pystyle/issues/45)) ([e539aea](https://github.com/gradienthealth/pystyle/commit/e539aea5bc2d5c42951fdf24effd5d725a9d6442))
* **PROC-2356:** leave a backtick span wrapped across source lines untouched ([#38](https://github.com/gradienthealth/pystyle/issues/38)) ([7447019](https://github.com/gradienthealth/pystyle/commit/7447019679c6a6046af21772383bcf7954054876))
* **PROC-2375:** count a class body as definition-time for RS019 ordering ([#49](https://github.com/gradienthealth/pystyle/issues/49)) ([f701561](https://github.com/gradienthealth/pystyle/commit/f7015617cc50f029b07b5e594daff76a45540c23))

## [0.4.0](https://github.com/gradienthealth/pystyle/compare/pystyle-v0.3.0...pystyle-v0.4.0) (2026-06-26)


### Features

* **NO-ISSUE:** add RS025 rejecting make_ outside test modules ([#30](https://github.com/gradienthealth/pystyle/issues/30)) ([7707a30](https://github.com/gradienthealth/pystyle/commit/7707a30f37f79e4e726932cf52109cc95bf5080c))
* **PROC-2318:** ban in-function imports in the shared ruff baseline ([#35](https://github.com/gradienthealth/pystyle/issues/35)) ([4bde651](https://github.com/gradienthealth/pystyle/commit/4bde65136b1d2fe281263f925fcce1befcc3047f))
* **PROC-2319:** add the RS027 too-many-positional-arguments rule ([#36](https://github.com/gradienthealth/pystyle/issues/36)) ([e3232e6](https://github.com/gradienthealth/pystyle/commit/e3232e6f1b29381b9ba74400eba23daa6b03a5ac))
* **PROC-2340:** add boolean-naming rules for prefix and embedded negation ([#29](https://github.com/gradienthealth/pystyle/issues/29)) ([87a3b19](https://github.com/gradienthealth/pystyle/commit/87a3b190aac2a082e06d6c6464504a36fc6aacb1))
* **PROC-2352:** add the RS028 exception-alias naming rule ([#33](https://github.com/gradienthealth/pystyle/issues/33)) ([aaab33a](https://github.com/gradienthealth/pystyle/commit/aaab33aac4fc72f4db58de9e707dbe33e7411f9e))
* **PROC-2356:** treat backticked references as atomic tokens when reflowing docstrings ([#37](https://github.com/gradienthealth/pystyle/issues/37)) ([42b42ad](https://github.com/gradienthealth/pystyle/commit/42b42ad4c496c6615af73d0dc1f8eb4bc92b9cc3))


### Documentation

* **NO-ISSUE:** add the judgment-conventions canon ([#31](https://github.com/gradienthealth/pystyle/issues/31)) ([fa99759](https://github.com/gradienthealth/pystyle/commit/fa99759b5f599a75bcce56a58a97b22e2a8d092b))

## [0.3.0](https://github.com/gradienthealth/pystyle/compare/pystyle-v0.2.0...pystyle-v0.3.0) (2026-06-25)


### ⚠ BREAKING CHANGES

* **NO-ISSUE:** rename the package and module from gradient-pystyle to pystyle ([#25](https://github.com/gradienthealth/pystyle/issues/25))

### Features

* **NO-ISSUE:** rename the package and module from gradient-pystyle to pystyle ([#25](https://github.com/gradienthealth/pystyle/issues/25)) ([909c7ef](https://github.com/gradienthealth/pystyle/commit/909c7efced3ccd26acba0d83ba5442ee86b8c085))
* **PROC-2277:** emit column offsets from gradient-pystyle violations ([e399129](https://github.com/gradienthealth/pystyle/commit/e3991294cd58ff45e9636e8c253445aeada81361))
* **PROC-2278:** add per-line and per-file suppression comments ([ba2b007](https://github.com/gradienthealth/pystyle/commit/ba2b0072bb82189e95a92fa32698e63665391ced))
* **PROC-2280:** add structure-aware RS009 reflow with --fix autofix ([#20](https://github.com/gradienthealth/pystyle/issues/20)) ([1c642e4](https://github.com/gradienthealth/pystyle/commit/1c642e40ea74e4c25f886e75e4a76f16b9845357))
* **PROC-2282:** enable Ruff D401 imperative-mood in the baseline ([43a89b7](https://github.com/gradienthealth/pystyle/commit/43a89b75772bb6e17d236a2fe6f33e4ad2d5ff85))
* **PROC-2301:** add complexity and size guardrails to ruff-base ([#5](https://github.com/gradienthealth/pystyle/issues/5)) ([d70c8d6](https://github.com/gradienthealth/pystyle/commit/d70c8d626026e469fa6b96fe7d946cdd8b4e53e4))
* **PROC-2302:** add cognitive-complexity and test-quality rules ([d04dc74](https://github.com/gradienthealth/pystyle/commit/d04dc746b36eaaefcb907fa67afaad1a96e392e7))
* **PROC-2303:** add the RS018 documentation-value signal ([2e8130a](https://github.com/gradienthealth/pystyle/commit/2e8130ab21781ebc4e01177284dc98c73efbf249))
* **PROC-2304:** scope lint enforcement to a PR's changed lines ([31427cb](https://github.com/gradienthealth/pystyle/commit/31427cb1eaee41878b83da174285580ba7467dfa))
* **PROC-2305:** add warn/error severity levels to gradient-pystyle rules ([439ec9c](https://github.com/gradienthealth/pystyle/commit/439ec9c829141ab38c18ea427db8fd3fa8f7904d))
* **PROC-2316:** add config-driven banned-import-by-path rule ([f24e957](https://github.com/gradienthealth/pystyle/commit/f24e9575513c7a18eb266c47d90d0b6114c2f193))
* **PROC-2320:** add a module and class element-ordering rule ([#22](https://github.com/gradienthealth/pystyle/issues/22)) ([cbfc170](https://github.com/gradienthealth/pystyle/commit/cbfc1704a0fc7633f2a21a7239162a0df5962e0d))
* **PROC-2338:** add documentation-form rules for comment-vs-docstring placement ([#24](https://github.com/gradienthealth/pystyle/issues/24)) ([4117a71](https://github.com/gradienthealth/pystyle/commit/4117a71847139fc627cf576ce2ec3a84cb27fe4d))
* **PROC-2339:** add a comment-tag format rule for special comments ([#23](https://github.com/gradienthealth/pystyle/issues/23)) ([bd91110](https://github.com/gradienthealth/pystyle/commit/bd91110b6ef8904ee5d7466bfe0faf1fe67f836a))

## [0.2.0](https://github.com/gradienthealth/gradient-pystyle/compare/gradient-pystyle-v0.1.0...gradient-pystyle-v0.2.0) (2026-06-24)


### Features

* **PROC-2301:** add complexity and size guardrails to ruff-base ([#5](https://github.com/gradienthealth/gradient-pystyle/issues/5)) ([d70c8d6](https://github.com/gradienthealth/gradient-pystyle/commit/d70c8d626026e469fa6b96fe7d946cdd8b4e53e4))
