# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0 (2025-11-15)


### ⚠ BREAKING CHANGES

* Media buy creation now FAILS when creatives are missing required fields (URL, dimensions) instead of silently skipping them.

### Features

* add 'asap' union type for start_time to support immediate campaign starts ([#338](https://github.com/adcontextprotocol/salesagent/issues/338)) ([72761f3](https://github.com/adcontextprotocol/salesagent/commit/72761f37a5a1ceb1249e731fba9203b61be5c600))
* add auth_header and timeout columns to creative_agents table ([#714](https://github.com/adcontextprotocol/salesagent/issues/714)) ([64eecd8](https://github.com/adcontextprotocol/salesagent/commit/64eecd834f0347aeee46b961c2f8730b37da207f))
* Add backward-compatible format_id namespacing with smart cache ([#382](https://github.com/adcontextprotocol/salesagent/issues/382)) ([a54ac1f](https://github.com/adcontextprotocol/salesagent/commit/a54ac1fc003f54494cb938fd3accc0de95be7db7))
* Add brand manifest policy system for flexible product discovery ([#663](https://github.com/adcontextprotocol/salesagent/issues/663)) ([1c00e1d](https://github.com/adcontextprotocol/salesagent/commit/1c00e1da7a24bba3b64e20c6534523d336e7815b))
* Add brand manifest policy UI dropdown in Admin ([#726](https://github.com/adcontextprotocol/salesagent/issues/726)) ([55d2414](https://github.com/adcontextprotocol/salesagent/commit/55d24145e8641c59baf9fa93330822ebd697910f))
* add commitizen for automated version management ([#666](https://github.com/adcontextprotocol/salesagent/issues/666)) ([4c49051](https://github.com/adcontextprotocol/salesagent/commit/4c49051cdea309b2ef20fd5eeb28fd6e3f5890ce))
* Add creative format size filtering with inventory-based suggestions ([#690](https://github.com/adcontextprotocol/salesagent/issues/690)) ([ced6466](https://github.com/adcontextprotocol/salesagent/commit/ced64664ff225d1c9c0ca3dcbd5e3a6fc90e473d))
* Add hierarchical product picker with search and caching ([#707](https://github.com/adcontextprotocol/salesagent/issues/707)) ([6a6c23d](https://github.com/adcontextprotocol/salesagent/commit/6a6c23d0a194862f84af4052d9daa58fa2f02183))
* Add inventory profiles for reusable inventory configuration ([#722](https://github.com/adcontextprotocol/salesagent/issues/722)) ([ceb2363](https://github.com/adcontextprotocol/salesagent/commit/ceb2363ca7f1879bb3f467d302ee44905194d40d))
* Add real-time custom targeting values endpoint and visual selector widget ([#678](https://github.com/adcontextprotocol/salesagent/issues/678)) ([ebd89b9](https://github.com/adcontextprotocol/salesagent/commit/ebd89b97868e9477ae624010304b417bd5b8d55f))
* Add signals agent registry with unified MCP client ([#621](https://github.com/adcontextprotocol/salesagent/issues/621)) ([9a15431](https://github.com/adcontextprotocol/salesagent/commit/9a15431f2a36663e93de4d2a94dcc7f7aef954c6))
* Add UX improvements to naming templates - live preview, presets, validation ([#306](https://github.com/adcontextprotocol/salesagent/issues/306)) ([cf5b10b](https://github.com/adcontextprotocol/salesagent/commit/cf5b10ba6e2ad18bf643254d715de64aefcc4ab5))
* alphabetize targeting keys/values and show display names ([#687](https://github.com/adcontextprotocol/salesagent/issues/687)) ([c6be06d](https://github.com/adcontextprotocol/salesagent/commit/c6be06d045bf4a4ff8063044827ef0006c9525dd))
* Auto-download AdCP schemas on workspace startup ([#616](https://github.com/adcontextprotocol/salesagent/issues/616)) ([94c3876](https://github.com/adcontextprotocol/salesagent/commit/94c3876ae67bc0759ef823d43e4028d765d28cf1))
* Complete GAM line item creation with format extensibility and creative association ([#313](https://github.com/adcontextprotocol/salesagent/issues/313)) ([2fd3ac7](https://github.com/adcontextprotocol/salesagent/commit/2fd3ac72cb64bd7df7bda1f4427e7504289478ea))
* Dynamic format discovery via CreativeAgentRegistry (AdCP v2.4) ([#358](https://github.com/adcontextprotocol/salesagent/issues/358)) ([7df11b2](https://github.com/adcontextprotocol/salesagent/commit/7df11b2f6af8ec41dd4dd8c212db473fae4fedb6))
* enforce strict AdCP v1 spec compliance for Creative model (BREAKING CHANGE) ([#706](https://github.com/adcontextprotocol/salesagent/issues/706)) ([ff1cbc4](https://github.com/adcontextprotocol/salesagent/commit/ff1cbc4732e5038b0493cfc90d1e2964de034707))
* improve product workflow - always show formats and descriptive targeting values ([#688](https://github.com/adcontextprotocol/salesagent/issues/688)) ([4530f25](https://github.com/adcontextprotocol/salesagent/commit/4530f253d24779aa4ef4f0ee3d527d3258bb28f3))
* refactor webhook deliveries ([f1302ba](https://github.com/adcontextprotocol/salesagent/commit/f1302ba66be517a999d0e00c78bce16046b6aebb))
* Remove Scope3 dependencies - make codebase vendor-neutral ([#668](https://github.com/adcontextprotocol/salesagent/issues/668)) ([de503bf](https://github.com/adcontextprotocol/salesagent/commit/de503bfda0e275cfc2273b93b757c47a9cbccd2c))
* Simplify targeting selector to match existing UI patterns ([#679](https://github.com/adcontextprotocol/salesagent/issues/679)) ([ce76f8e](https://github.com/adcontextprotocol/salesagent/commit/ce76f8e2ca01070f3f281aa5f9a69d83789af768))
* support application level context ([#735](https://github.com/adcontextprotocol/salesagent/issues/735)) ([ea6891d](https://github.com/adcontextprotocol/salesagent/commit/ea6891d8091f2e178330802293859bf93b3838bc))
* Update budget handling to match AdCP v2.2.0 specification ([#635](https://github.com/adcontextprotocol/salesagent/issues/635)) ([0a9dd4a](https://github.com/adcontextprotocol/salesagent/commit/0a9dd4a160deca71508aa83e3e8f5b56b5198e14))


### Bug Fixes

* Achieve 100% mypy compliance in src/ directory - 881 errors to 0 ([#662](https://github.com/adcontextprotocol/salesagent/issues/662)) ([d7f4711](https://github.com/adcontextprotocol/salesagent/commit/d7f47112fa0fe221447bd470d4daeb4783f86b75))
* ad unit format button, targeting selector crash, and service account auth ([#723](https://github.com/adcontextprotocol/salesagent/issues/723)) ([83bd497](https://github.com/adcontextprotocol/salesagent/commit/83bd497469eaa30eeba28e3960137fc6ebbbe498))
* AdCP responses now exclude None values in JSON serialization ([#642](https://github.com/adcontextprotocol/salesagent/issues/642)) ([c3fa69a](https://github.com/adcontextprotocol/salesagent/commit/c3fa69a511db5942ee307dcad6c1fe5cf6b06246))
* AdCP responses now properly omit null/empty optional fields ([#638](https://github.com/adcontextprotocol/salesagent/issues/638)) ([ab7c4cd](https://github.com/adcontextprotocol/salesagent/commit/ab7c4cdaed47c3f3ce85de845914051d3a08197d))
* Add /admin prefix to OAuth redirect URI for nginx routing ([#651](https://github.com/adcontextprotocol/salesagent/issues/651)) ([a95a534](https://github.com/adcontextprotocol/salesagent/commit/a95a5344d38667d0e4209dff3f7345d637ed8fbe))
* Add content hash verification to prevent meta file noise ([#659](https://github.com/adcontextprotocol/salesagent/issues/659)) ([20b0a16](https://github.com/adcontextprotocol/salesagent/commit/20b0a165b7fea7a8da33840806bc03ef612fc32d))
* Add logging + fix targeting browser sync button ([#677](https://github.com/adcontextprotocol/salesagent/issues/677)) ([bdf19cc](https://github.com/adcontextprotocol/salesagent/commit/bdf19cccfe177429f0420793ee2eae3206eed157))
* Add missing /api/tenant/&lt;tenant_id&gt;/products endpoint ([9dc4bdc](https://github.com/adcontextprotocol/salesagent/commit/9dc4bdcf3787a40a921d1c5374a2f3da1776c0fb))
* Add missing activity feed and audit logs to manual approval path ([#729](https://github.com/adcontextprotocol/salesagent/issues/729)) ([114778c](https://github.com/adcontextprotocol/salesagent/commit/114778c85d009333d30b7640b623a11bd8ee0d6f))
* Add missing adapter_type to SyncJob creation ([fb0fb79](https://github.com/adcontextprotocol/salesagent/commit/fb0fb7905699503087180af91acf8190c2fa4bfa))
* Add null safety checks for audience.type and audience.segment_type ([#682](https://github.com/adcontextprotocol/salesagent/issues/682)) ([b8e6e77](https://github.com/adcontextprotocol/salesagent/commit/b8e6e77a4aea4a2589e7e1fddc73f6346e2729c2))
* Add timeout to discover_ad_units to prevent stuck syncs ([56457ad](https://github.com/adcontextprotocol/salesagent/commit/56457ad07c329064b451869b2e25134a401bb0d3))
* apply type filter when fetching inventory by IDs ([3fc3ded](https://github.com/adcontextprotocol/salesagent/commit/3fc3ded211a5137c932fbd20be18b36a35a19e46))
* approval flow ([ee2e90a](https://github.com/adcontextprotocol/salesagent/commit/ee2e90acfb204478b1c1bcc5c52e07ee97e78cce))
* Auto-create user records for authorized emails on tenant login ([#492](https://github.com/adcontextprotocol/salesagent/issues/492)) ([454eb8f](https://github.com/adcontextprotocol/salesagent/commit/454eb8ffbb015b63e958f86d17361c0462358b32))
* Check super admin status before signup flow redirect ([#674](https://github.com/adcontextprotocol/salesagent/issues/674)) ([e5dfb8d](https://github.com/adcontextprotocol/salesagent/commit/e5dfb8dc4c98bf426f463f01992b31aab9bab3de))
* Clean up smoke tests and resolve warnings ([#629](https://github.com/adcontextprotocol/salesagent/issues/629)) ([73cbc99](https://github.com/adcontextprotocol/salesagent/commit/73cbc99d4ed8c8385b0b09b0ce5e43fa7ecc006b))
* Complete /admin prefix handling for all API calls ([#736](https://github.com/adcontextprotocol/salesagent/issues/736)) ([4c20c9c](https://github.com/adcontextprotocol/salesagent/commit/4c20c9c6e68d953f1548fe2253338b4d67dc18e1))
* Convert FormatReference to FormatId in MediaPackage reconstruction ([#656](https://github.com/adcontextprotocol/salesagent/issues/656)) ([7c24705](https://github.com/adcontextprotocol/salesagent/commit/7c247053d94abbce15331b4df05069636ad1409f))
* Convert summary dict to JSON string in sync completion ([3318ee0](https://github.com/adcontextprotocol/salesagent/commit/3318ee0bed23bb1a21d2f2cb8870d73d59234dac))
* convert to utc ([bcb54f0](https://github.com/adcontextprotocol/salesagent/commit/bcb54f01bba60ac6862332942d09ee332387b3a5))
* Correct AdManagerClient signature for service account auth ([#571](https://github.com/adcontextprotocol/salesagent/issues/571)) ([bcb1686](https://github.com/adcontextprotocol/salesagent/commit/bcb1686fa8c23492db73a63e87d088f5ae6c6246)), closes [#570](https://github.com/adcontextprotocol/salesagent/issues/570)
* Correct API field name mismatch in targeting selector widget ([#681](https://github.com/adcontextprotocol/salesagent/issues/681)) ([9573749](https://github.com/adcontextprotocol/salesagent/commit/9573749beb05d260b0786479c68b479c85807c56))
* creative agent url check; allow to fallback to /mcp when creating mcp client ([09bc1ac](https://github.com/adcontextprotocol/salesagent/commit/09bc1ac6782faf1362ba253f23785c842aa771d7))
* creative agent url check; allow to fallback to /mcp when creating mcp client ([6bf221f](https://github.com/adcontextprotocol/salesagent/commit/6bf221f501fb6f700d2092bf83cca58884deb365))
* creative approval/rejection webhook delivery ([9062449](https://github.com/adcontextprotocol/salesagent/commit/9062449959bfcca02f1d3377b5f9f8c962917d57))
* Creative management - reject invalid creatives ([#460](https://github.com/adcontextprotocol/salesagent/issues/460)) ([1540de3](https://github.com/adcontextprotocol/salesagent/commit/1540de3946f6de9b22fd37e9b08077f006c86894))
* display and save custom targeting keys in product inventory ([#692](https://github.com/adcontextprotocol/salesagent/issues/692)) ([991656b](https://github.com/adcontextprotocol/salesagent/commit/991656b31702016d744a6e1bda75674a24b4fee8))
* Docker test cleanup to prevent 100GB+ resource accumulation ([9036cae](https://github.com/adcontextprotocol/salesagent/commit/9036cae83ccd3d930582cd79f11db629e8b5b4df))
* Docker test cleanup to prevent 100GB+ resource accumulation ([9ed12fd](https://github.com/adcontextprotocol/salesagent/commit/9ed12fdf33ede9aed33e692894a0ea65387f2d32))
* Enable all 189 integration_v2 tests - achieve 100% coverage goal ([#626](https://github.com/adcontextprotocol/salesagent/issues/626)) ([6377462](https://github.com/adcontextprotocol/salesagent/commit/6377462815745643b24d8c40058824261e6d863f))
* enforce brand_manifest_policy in get_products ([#731](https://github.com/adcontextprotocol/salesagent/issues/731)) ([075e681](https://github.com/adcontextprotocol/salesagent/commit/075e6811251861849002c557b78ab9ec251eb5d2))
* ensure User record creation during OAuth tenant selection ([#701](https://github.com/adcontextprotocol/salesagent/issues/701)) ([be22ffb](https://github.com/adcontextprotocol/salesagent/commit/be22ffb675032fe26610fc037b50e32620de7700))
* Exclude null values from list_authorized_properties response ([#647](https://github.com/adcontextprotocol/salesagent/issues/647)) ([5afb6b5](https://github.com/adcontextprotocol/salesagent/commit/5afb6b5a0544e117da8ce1a439d40a36eb0fe629))
* fetch inventory by IDs to bypass 500-item API limit ([c1e197e](https://github.com/adcontextprotocol/salesagent/commit/c1e197eb6d1882c317ef96b13de5d7b4dcf42418))
* fetch specific ad units by ID for placement size extraction ([85f792d](https://github.com/adcontextprotocol/salesagent/commit/85f792ded5a47a2d1de0cbf351ef1eccbc31b590))
* file lint error ([#625](https://github.com/adcontextprotocol/salesagent/issues/625)) ([2fec26e](https://github.com/adcontextprotocol/salesagent/commit/2fec26eaf3cd51faa98100264a80d87c8c437980))
* flush deleted inventory mappings before recreating ([c83e34c](https://github.com/adcontextprotocol/salesagent/commit/c83e34c8aa1712b0ec4c0f386554595f9f134255))
* GAM adapter ([f4f0df1](https://github.com/adcontextprotocol/salesagent/commit/f4f0df1bc33edd4d37e1d800ba07a66df6e92c55))
* GAM adpaters and other logic changes including bumping adcp client to 2.5.5 ([8367e0a](https://github.com/adcontextprotocol/salesagent/commit/8367e0a1f9d52e04ce41f81cb35bfd91c33fbcdc))
* GAM advertiser search and pagination with Select2 UI ([#710](https://github.com/adcontextprotocol/salesagent/issues/710)) ([792d4ae](https://github.com/adcontextprotocol/salesagent/commit/792d4ae31a27452e8043ae6b4e9baa493c9e37a5))
* GAM product placements not saving when line_item_type absent ([#691](https://github.com/adcontextprotocol/salesagent/issues/691)) ([eb66e33](https://github.com/adcontextprotocol/salesagent/commit/eb66e3313c9dd0fbbdfe8ff7c0b6674463e2bdd2))
* Handle /admin prefix in login redirects and API calls ([#733](https://github.com/adcontextprotocol/salesagent/issues/733)) ([15ab582](https://github.com/adcontextprotocol/salesagent/commit/15ab582e94dfdc7ed5b318bf4d2dec91b517551e))
* Handle CreateMediaBuyError response in approval and main flows ([#745](https://github.com/adcontextprotocol/salesagent/issues/745)) ([574943b](https://github.com/adcontextprotocol/salesagent/commit/574943b88ff076fbb0d2b9d932cde49a96e2e497))
* Handle unrestricted agents in property discovery (no property_ids = all properties) ([#750](https://github.com/adcontextprotocol/salesagent/issues/750)) ([136575b](https://github.com/adcontextprotocol/salesagent/commit/136575b6dcebaaea0782f9a0edf263126881daa2))
* Implement creative assignment in update_media_buy ([#560](https://github.com/adcontextprotocol/salesagent/issues/560)) ([99cdcdc](https://github.com/adcontextprotocol/salesagent/commit/99cdcdc741be6e103e8db3dcefa36854a63facc8))
* Implement missing update_media_buy field persistence ([#749](https://github.com/adcontextprotocol/salesagent/issues/749)) ([f67a304](https://github.com/adcontextprotocol/salesagent/commit/f67a304690067608eda74c796cf2deff4d0448d6))
* Import get_testing_context in list_authorized_properties ([#632](https://github.com/adcontextprotocol/salesagent/issues/632)) ([6612c7d](https://github.com/adcontextprotocol/salesagent/commit/6612c7d1870bdcf05b328452c10e44796c35a92c))
* improve creative status handling and dashboard visibility ([#711](https://github.com/adcontextprotocol/salesagent/issues/711)) ([539e1bb](https://github.com/adcontextprotocol/salesagent/commit/539e1bbb926c92e390a1a97529db5640b17134d0))
* improve inventory browser UX and fix search lag ([#709](https://github.com/adcontextprotocol/salesagent/issues/709)) ([0d09f1b](https://github.com/adcontextprotocol/salesagent/commit/0d09f1bcbc024acc13a7cdab3df2e105ec18a92a))
* include ALL statuses when fetching inventory names for existing products ([2a61600](https://github.com/adcontextprotocol/salesagent/commit/2a616008f2d903c550e4d3e3e5e5c8fb5271f91d))
* Include service_account_email in adapter_config dict for template ([#517](https://github.com/adcontextprotocol/salesagent/issues/517)) ([c36aef6](https://github.com/adcontextprotocol/salesagent/commit/c36aef618c21720e2399dff996fa10f6f7d98bd2))
* Integration tests, mypy errors, and AdCP schema compliance ([#633](https://github.com/adcontextprotocol/salesagent/issues/633)) ([77c4da6](https://github.com/adcontextprotocol/salesagent/commit/77c4da632b35b806452b89bdafd1bce781699fff))
* Integration tests, mypy errors, and deprecation warnings ([#628](https://github.com/adcontextprotocol/salesagent/issues/628)) ([be52151](https://github.com/adcontextprotocol/salesagent/commit/be521514a146ae765c879f7ad3b84d4c9358462e))
* Integration tests, mypy errors, and test infrastructure improvements ([#631](https://github.com/adcontextprotocol/salesagent/issues/631)) ([ca4c184](https://github.com/adcontextprotocol/salesagent/commit/ca4c1846d38a95442d1ec7d89710a2a8ffdf5d6d))
* inventory sync ([d300258](https://github.com/adcontextprotocol/salesagent/commit/d300258260bd64f7aaaf75f0d1c359380783f153))
* Inventory sync JavaScript errors ([0d2ad1f](https://github.com/adcontextprotocol/salesagent/commit/0d2ad1ff915a30849534eaf66318518166a49edc))
* inventory sync status now checks GAMInventory table instead of Products ([#708](https://github.com/adcontextprotocol/salesagent/issues/708)) ([193e87d](https://github.com/adcontextprotocol/salesagent/commit/193e87d0cf3c4ca0cab1d5edc16911a0def1711b))
* Load pricing_options when querying products ([#413](https://github.com/adcontextprotocol/salesagent/issues/413)) ([a87c69a](https://github.com/adcontextprotocol/salesagent/commit/a87c69aee9568835cd599d3de7754f6c632c696e))
* make media_buy_ids optional in get_media_buy_delivery per AdCP spec ([#704](https://github.com/adcontextprotocol/salesagent/issues/704)) ([5c69013](https://github.com/adcontextprotocol/salesagent/commit/5c690131d9d90a59acc47e10954768adf9456cff))
* media buys & creatives ([58c4f45](https://github.com/adcontextprotocol/salesagent/commit/58c4f45901abfaa3458336c23ec69e5c569efe7d))
* mypy ([77b5ecc](https://github.com/adcontextprotocol/salesagent/commit/77b5ecc2fd215ba7761dcd9437f1049a497ca3ac))
* Normalize agent URL variations for consistent validation ([#497](https://github.com/adcontextprotocol/salesagent/issues/497)) ([9bef942](https://github.com/adcontextprotocol/salesagent/commit/9bef94207b271f9436347536c1df4dc5ba9f0f8c))
* parse and apply custom targeting from product forms to GAM line items ([#686](https://github.com/adcontextprotocol/salesagent/issues/686)) ([a1132ae](https://github.com/adcontextprotocol/salesagent/commit/a1132aef30c7bdf8fb1ceefee8721217c4f31aef))
* persist targeting and placement selections in product editor ([#689](https://github.com/adcontextprotocol/salesagent/issues/689)) ([ebbecf0](https://github.com/adcontextprotocol/salesagent/commit/ebbecf047e56b3ea6004d5721f23421b029c4363))
* populate custom targeting keys when editing products ([#693](https://github.com/adcontextprotocol/salesagent/issues/693)) ([88f0b9e](https://github.com/adcontextprotocol/salesagent/commit/88f0b9ea6df0f1507638d7f46674e7c1dd7b3f45))
* prevent duplicate IDs in placement display after removal ([#696](https://github.com/adcontextprotocol/salesagent/issues/696)) ([87b0eac](https://github.com/adcontextprotocol/salesagent/commit/87b0eac31f4f2b788f6c01e4ad6887a2fa30fcf3))
* Prevent duplicate tenant display when user has both domain and email access ([#660](https://github.com/adcontextprotocol/salesagent/issues/660)) ([92ca049](https://github.com/adcontextprotocol/salesagent/commit/92ca049e0d34c77d0473430f50129bbbaedc2553))
* product editor bugs - JSON parsing, text color, selection preservation ([#694](https://github.com/adcontextprotocol/salesagent/issues/694)) ([50765cf](https://github.com/adcontextprotocol/salesagent/commit/50765cfd83b581a4e7141dd7e837e6a57ff48bae))
* rebase ([581b18b](https://github.com/adcontextprotocol/salesagent/commit/581b18b4a49bc811329534dcde1f0d3b81ce2f76))
* Reduce skipped tests from 323 to ~97 (70% improvement) ([#669](https://github.com/adcontextprotocol/salesagent/issues/669)) ([c48f978](https://github.com/adcontextprotocol/salesagent/commit/c48f978f427d17b3092261d67d823fff18093d61))
* rejection ([79cb754](https://github.com/adcontextprotocol/salesagent/commit/79cb754c6240dd8370a73642bdf8f6caa5f5aca8))
* remove /a2a suffix from A2A endpoint URLs and add name field to configs ([2b036c6](https://github.com/adcontextprotocol/salesagent/commit/2b036c6fc44a3316d15e82c0245d70d447b7142c))
* remove /a2a suffix from A2A endpoint URLs and add name field to configs ([13914b8](https://github.com/adcontextprotocol/salesagent/commit/13914b8584dea3d17c8e751ad7d7db58c2b3e2b2))
* Remove auto-restart of delivery simulators on server boot ([#646](https://github.com/adcontextprotocol/salesagent/issues/646)) ([52c2378](https://github.com/adcontextprotocol/salesagent/commit/52c2378d20620a2ab55f125d6a0f87ead73ccb02))
* remove dead API docs link and fix testing docs path ([#700](https://github.com/adcontextprotocol/salesagent/issues/700)) ([9fd959e](https://github.com/adcontextprotocol/salesagent/commit/9fd959eed4c98a9d6ddb7f3fbb5abbba02cc99a7)), closes [#676](https://github.com/adcontextprotocol/salesagent/issues/676)
* Remove fake media_buy_id from pending/async responses in mock adapter ([#658](https://github.com/adcontextprotocol/salesagent/issues/658)) ([dc2a2ba](https://github.com/adcontextprotocol/salesagent/commit/dc2a2ba63dca42e36f0d6b6cae6a9d23c22468cb))
* remove inventory sync requirement for mock adapter ([#719](https://github.com/adcontextprotocol/salesagent/issues/719)) ([4268b2e](https://github.com/adcontextprotocol/salesagent/commit/4268b2e9a93a499ec6b03518b8c3c3fd42361568))
* Remove non-existent fields from SyncCreativesResponse ([9bf3da7](https://github.com/adcontextprotocol/salesagent/commit/9bf3da7b358d55739e9687d50b0a62f0a7d5ce22))
* Remove non-existent fields from SyncCreativesResponse ([453c329](https://github.com/adcontextprotocol/salesagent/commit/453c329b40899fdcaea9bffc1fc766875a1b963b))
* Remove non-existent impressions field from AdCPPackageUpdate ([#500](https://github.com/adcontextprotocol/salesagent/issues/500)) ([404c653](https://github.com/adcontextprotocol/salesagent/commit/404c6539b7a915b1df47ea797bd181c70aac6312))
* Remove non-spec tags field from ListAuthorizedPropertiesResponse ([#643](https://github.com/adcontextprotocol/salesagent/issues/643)) ([a38b3d7](https://github.com/adcontextprotocol/salesagent/commit/a38b3d751ecb3bf55983020ec52d08a4fc20053c))
* remove top-level budget requirement from create_media_buy ([#725](https://github.com/adcontextprotocol/salesagent/issues/725)) ([4474de3](https://github.com/adcontextprotocol/salesagent/commit/4474de3d1cf724c6dddc6b0bc77c999015e1acd3))
* Replace progress_data with progress in SyncJob ([f4008f4](https://github.com/adcontextprotocol/salesagent/commit/f4008f430fddc6acb1822ac9c68875e17bc5c99c))
* require authentication for sync_creatives and update_media_buy ([#721](https://github.com/adcontextprotocol/salesagent/issues/721)) ([defa383](https://github.com/adcontextprotocol/salesagent/commit/defa3837a52bede3635a3d1d3f74eb0e84c37972))
* Resolve GAM inventory sync and targeting data loading issues ([#675](https://github.com/adcontextprotocol/salesagent/issues/675)) ([ca31c6a](https://github.com/adcontextprotocol/salesagent/commit/ca31c6a6334d0db9afa3beadefdfb5d77429f503))
* Restore accidentally deleted commitizen configuration files ([c92075c](https://github.com/adcontextprotocol/salesagent/commit/c92075c8c9d2602484cb3153fdbbd5460e4fa0f2))
* Restore brand manifest policy migrations and merge with signals agent ([e30c106](https://github.com/adcontextprotocol/salesagent/commit/e30c106c9517fa342a06ca0ace829b63780532a9))
* Return human-readable text in MCP protocol messages ([#644](https://github.com/adcontextprotocol/salesagent/issues/644)) ([3bb9bce](https://github.com/adcontextprotocol/salesagent/commit/3bb9bcedef3d9d19e3564f76847468ced02bf812))
* Route external domains to tenant login instead of signup ([#661](https://github.com/adcontextprotocol/salesagent/issues/661)) ([b194b83](https://github.com/adcontextprotocol/salesagent/commit/b194b83757250efce28f07da7496ef681a18a73f))
* sales agent logic ([0a51476](https://github.com/adcontextprotocol/salesagent/commit/0a51476a9411f7f31d7daa495322b071bda91ca3))
* Set session role for super admin OAuth login ([#654](https://github.com/adcontextprotocol/salesagent/issues/654)) ([505b24f](https://github.com/adcontextprotocol/salesagent/commit/505b24f45a2d9cf573e8726ea011f51cba7a1c27))
* Set tenant context when x-adcp-tenant header provides direct tenant_id ([#467](https://github.com/adcontextprotocol/salesagent/issues/467)) ([20b3f9c](https://github.com/adcontextprotocol/salesagent/commit/20b3f9c88171643ed8e8f0117029fb94eb63ff41))
* show both name and ID for placements consistently ([#695](https://github.com/adcontextprotocol/salesagent/issues/695)) ([52caddd](https://github.com/adcontextprotocol/salesagent/commit/52caddd69f0785fd9cd2a8b7d1c9e742c3766f47))
* signals agent test endpoint async handling ([#718](https://github.com/adcontextprotocol/salesagent/issues/718)) ([e1c5d72](https://github.com/adcontextprotocol/salesagent/commit/e1c5d722db002c22d16ad28f6f272b2aafa08359))
* Stop auto-generating buyer_ref - it's the buyer's identifier ([#302](https://github.com/adcontextprotocol/salesagent/issues/302)) ([0866178](https://github.com/adcontextprotocol/salesagent/commit/0866178d973f2d1c293f360c65c237109a13fc34))
* syntax ([af504a6](https://github.com/adcontextprotocol/salesagent/commit/af504a690ad2ad4da7a660308a089869969a97f6))
* Targeting browser, product page auth, UI repositioning + format conversion tests ([#683](https://github.com/adcontextprotocol/salesagent/issues/683)) ([d363627](https://github.com/adcontextprotocol/salesagent/commit/d3636275cbf5b1ac2aae50fa91639b221993a38c))
* targeting keys errors in browser and product pages ([#685](https://github.com/adcontextprotocol/salesagent/issues/685)) ([7fc3603](https://github.com/adcontextprotocol/salesagent/commit/7fc3603c63f9d0a870b5b36fd86763bcb277dfb7))
* test ([62c2fe0](https://github.com/adcontextprotocol/salesagent/commit/62c2fe0bca0fd7416770689929986385f10d52a2))
* test scase in test_format_conversion_approval ([3060a24](https://github.com/adcontextprotocol/salesagent/commit/3060a243664408ee26ef2cb4fcd90638022f3389))
* tests ([f70f684](https://github.com/adcontextprotocol/salesagent/commit/f70f6845447bd920fed134d68d736fa1f818b131))
* tests ([c966e43](https://github.com/adcontextprotocol/salesagent/commit/c966e43d21987bae837bb5eac19c52ee95122f54))
* Unskip 3 integration tests and reduce mypy errors by 330 ([#627](https://github.com/adcontextprotocol/salesagent/issues/627)) ([37cc165](https://github.com/adcontextprotocol/salesagent/commit/37cc1656a3ffd192dd127d68aff7cc1194b86bed))
* Update DNS widget to use A record pointing to Approximated proxy IP ([#636](https://github.com/adcontextprotocol/salesagent/issues/636)) ([3291ae6](https://github.com/adcontextprotocol/salesagent/commit/3291ae684174cc8d2d6de4188a384fc18b9ddeb2))
* Update tenant selector template to work with dictionary objects ([#652](https://github.com/adcontextprotocol/salesagent/issues/652)) ([aa612a3](https://github.com/adcontextprotocol/salesagent/commit/aa612a35aae011f638ed906ac2c71b0a50d3757d))
* Use content-based hashing for schema sync to avoid metadata noise ([#649](https://github.com/adcontextprotocol/salesagent/issues/649)) ([5625955](https://github.com/adcontextprotocol/salesagent/commit/5625955d913bb6ea4264c04d0ba9d4767f9a57fd))
* use correct field name inventory_metadata in IDs path ([4e7d7a2](https://github.com/adcontextprotocol/salesagent/commit/4e7d7a2344d2553e9396ff53de7031fcf7e9873b))
* Use SQLAlchemy event listener for statement_timeout with PgBouncer ([#641](https://github.com/adcontextprotocol/salesagent/issues/641)) ([bde8186](https://github.com/adcontextprotocol/salesagent/commit/bde8186e1d182cd0279b1e0c772fb79fa09654ea))
* wrap service account credentials with GoogleCredentialsClient ([#727](https://github.com/adcontextprotocol/salesagent/issues/727)) ([9d21709](https://github.com/adcontextprotocol/salesagent/commit/9d2170948c9efd844b4f1a7ef658935860947351))

## [Unreleased]

### Added
- Changeset system for automated version management
- CI workflows to enforce changeset requirements on PRs
- Automated version bump PR creation when changesets are merged

## [0.1.0] - 2025-01-29

Initial release of the AdCP Sales Agent reference implementation.

### Added
- MCP server implementation with AdCP v2.3 support
- A2A (Agent-to-Agent) protocol support
- Multi-tenant architecture with PostgreSQL
- Google Ad Manager (GAM) adapter
- Mock ad server adapter for testing
- Admin UI with Google OAuth authentication
- Comprehensive testing backend with dry-run support
- Real-time activity dashboard with SSE
- Workflow management system
- Creative management and approval workflows
- Audit logging
- Docker deployment support
- Extensive documentation

[Unreleased]: https://github.com/adcontextprotocol/salesagent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/adcontextprotocol/salesagent/releases/tag/v0.1.0
