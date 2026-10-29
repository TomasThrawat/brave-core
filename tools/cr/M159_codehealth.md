# M159 code health follow-ups

Tasks found by reviewing upstream changes in `158.0.8127.2..159.0.8131.1` (2696
commits) for regressions, deprecations and code-health migrations that apply to
Brave. Tick items off as they land.

## 1. Regressions

### History embeddings database deleted on every startup

[53a3eaccd455](https://chromium.googlesource.com/chromium/src/+/53a3eaccd455f1f0e8eb99f8bb50c3576aa28825)
adds `DeleteHistoryEmbeddingsDatabase()` to
`ChromeBrowserMainParts::PostProfileInit()`. It posts a task that deletes
`<profile>/HistoryEmbeddings` on desktop and Android, as upstream retires
History Embeddings (bug 571719847). Brave still uses the feature for Leo and
semantic history search: `BraveHistoryEmbeddingsService` subclasses upstream's
service, which opens its `SqlDatabase` at
`history_service_->history_dir().Append(kHistoryEmbeddingsName)`
(`"HistoryEmbeddings"`, `components/history_embeddings/core/sql_database.h:28`),
and `history_dir()` is the profile path. Nothing in Brave stops the deletion, so
the on-device index is lost on every launch. Verified statically.

- [ ] `chrome/browser/chrome_browser_main.cc`: skip
      `DeleteHistoryEmbeddingsDatabase()` (plaster on the `PostTask`, or the
      existing `patches/chrome-browser-chrome_browser_main.cc.patch`)
- [ ] Add a browser test with a `PRE_` step checking that the
      `HistoryEmbeddings` database survives a restart
- [ ] Watch bug 571719847 for the removal of `components/history_embeddings`,
      which Leo's history search builds on

### Android APK `versionName` is no longer Brave's version

[af2262c48efe](https://chromium.googlesource.com/chromium/src/+/af2262c48efef6035061807f28bc5e2b9b5ccf49)
removed the `android_override_version_{code,name}` GN args. Brave still sets
`android_override_version_name`, and GN only warns "Build argument has no
effect": cr159's
`out/android_Static/gen/chrome/android/chrome_public_apk.build_config.json` has
`"version_name": "159.1.101.0"` instead of `1.101.0`. `version_code` is
unaffected.

- [ ] Restore Brave's version name, with a plaster on `version_name` in
      `chrome/android/chrome_public_apk_tmpl.gni` (or `chrome/version.gni`), and
      check the built manifest
- [ ] Drop `android_override_version_name` from
      `build/commands/lib/buildArgs.ts:248`, `buildOptions.ts:87` and
      `config.ts:74,203,509-510`

### iOS: Safari CSV importer includes the deleted `csv_password_iterator.h`

[4250522f0ff4](https://chromium.googlesource.com/chromium/src/+/4250522f0ff4c88e82af7ac1a68c719bc5045ef9)
folded `CSVPasswordIterator` into `CSVPasswordSequence`, deleted
`csv_password_iterator.h`, and made `ConsumeCSVLine()` file-local with a
`std::string_view&` parameter. Brave's
`//brave/components/password_manager/core/browser/import:csv` is only reached
from `ios/browser/api/password/importer`, so Linux and Android build and iOS
won't.

- [ ] `components/password_manager/core/browser/import/csv_safari_password_iterator.cc:13,24`
- [ ] `components/password_manager/core/browser/import/csv_safari_password_sequence.cc:22,101`:
      give Brave its own `ConsumeCSVLine` and drop the include

### Android toolbar "close all tabs" still closes pinned tabs

[770b3e6754b6](https://chromium.googlesource.com/chromium/src/+/770b3e6754b6667fd90e7b3a9dbe67ce639c139b)
enabled `AndroidCloseAllTabsRetainsPinnedTabs` (C++ and the Java safe default).
Upstream's `CloseAllTabsHelper` and `CloseAllTabsDialog` now keep pinned tabs
and handle archived tabs. Brave's bottom toolbar action builds its own
`TabClosureParams.closeAllTabs()`, so it still closes pinned tabs, unlike every
upstream entry point.

- [ ] `android/java/org/chromium/chrome/browser/toolbar/BraveToolbarManager.java:500`:
      route `closeAllTabsAction` through `CloseAllTabsHelper`, or decide that
      Brave's action keeps closing pinned tabs

## 2. Upcoming deprecations

### iOS factories move to `BuildServiceInstanceFor(ProfileIOS&)`

Extends M158's "iOS: `GetForProfile(ProfileIOS&)`", whose trigger fired: 39
"[ios] Use ProfileIOS& in XFactory" commits (bug 576182342), e.g.
[80a95487fe61](https://chromium.googlesource.com/chromium/src/+/80a95487fe61f73977bab6447e246c6dc5bbdfdf).
Upstream files overriding the pointer form went from 496 to 414, and the
reference form from 4 to 88.
`ios/chrome/browser/shared/model/profile/internal/profile_keyed_service_factory_ios.h:112`
says "Remove overloads and make pure virtual once all sub-classes have been
converted". Then every Brave pointer override stops compiling, and lifts don't
build iOS.

- [ ] Move Brave's 16 iOS factories to the reference form:
      `ios/browser/ai_chat/{ai_chat_service,model_service,tab_tracker_service}_factory`,
      `ios/browser/api/webcompat_reporter/webcompat_reporter_service_factory`,
      `ios/browser/brave_account/brave_account_service_factory_ios`,
      `ios/browser/brave_ads/ads_service_factory_ios`,
      `ios/browser/brave_origin/brave_origin_service_factory`,
      `ios/browser/brave_shields/brave_shields_settings_service_factory`,
      `ios/browser/brave_wallet/brave_wallet_service_factory`,
      `ios/browser/debounce/debounce_service_factory`,
      `ios/browser/favicon/brave_ios_favicon_loader_factory`,
      `ios/browser/misc_metrics/profile_misc_metrics_service_factory`,
      `ios/browser/serp_metrics/serp_metrics_service_factory_ios`,
      `ios/browser/skus/skus_service_factory` and
      `ios/browser/url_sanitizer/url_sanitizer_service_factory`
- [ ] `chromium_src/ios/chrome/browser/metrics/model/google_groups_manager_factory.mm:18`
      and
      `chromium_src/ios/chrome/browser/signin/model/about_signin_internals_factory.cc:21`
      stub upstream's pointer form to return null; switch them when upstream
      converts those factories

### Settings Refresh 2026 would break Brave's settings routes

[c3f34b179536](https://chromium.googlesource.com/chromium/src/+/c3f34b1795367)
makes the refresh drop the onStartup, defaultBrowser, downloads, system and
reset routes, add `/general` and move People to `/`, with nested templates in
`settings_menu.html.ts` and `settings_main.html.ts`
(`settingsRefresh2026Enabled_`: 0 uses at 158.0.8127.2, 17 at 159.0.8131.1).
`IsSettingsRefresh2026Enabled()` is
`kSettingsRefresh2026 && (kDesktopGlowUp || kWebuiRefresh2026)`, all disabled by
default and none pinned by Brave. A flip or field trial would break Brave's
settings pages, the `route.ts` patch and the `settings_menu`/`settings_main`
manglers. "[cr159][Settings] Keep Search after Sync in the menu" already handles
Search in both variants.

- [ ] Pin `kSettingsRefresh2026` disabled (plaster on
      `chrome/browser/ui/ui_features.cc`) with a desktop-only
      `app/feature_defaults_unittest.cc` entry
- [ ] Consider pinning `kWebuiRefresh2026` and `kDesktopGlowUp`, which also gate
      other refresh UI

### Leo's content agent would get the Actor file upload tool

[e58bb5d4ba1e](https://chromium.googlesource.com/chromium/src/+/e58bb5d4ba1e)
implements `FileUploadTool`: the browser downloads each file, with the user's
credentials for Google hosts by default, intercepts the page's file chooser and
clicks the target. It's behind `actor::kGlicActorFileUploadTool` (disabled),
checked in `actor::BuildToolRequest()`
(`chrome/browser/actor/actor_proto_conversion.cc:531`), which Brave's content
agent calls (`browser/ai_chat/content_agent_tool_provider.cc:218`). Brave pins
no `kGlicActor*` feature, so a default flip hands Leo a tool Brave never
reviewed.

- [ ] Pin `kGlicActorFileUploadTool` disabled (plaster on
      `components/actor/core/actor_features.cc`) with an
      `app/feature_defaults_unittest.cc` entry, or evaluate it for the agent
- [ ] Consider pinning the other `kGlicActor*` tool features reachable through
      `BuildToolRequest()`

### Declarative `windowfeatures` skips Brave's window farbling

[2c1550b7e369](https://chromium.googlesource.com/chromium/src/+/2c1550b7e369a067675f6b928f5acbb8fd9147f7)
adds a `windowfeatures` attribute on `<a>`, `<area>` and `<form>`, parsed by the
new `GetWindowFeaturesFromAttribute()`, which accepts width, height, left and
top. Brave's
`chromium_src/third_party/blink/renderer/core/page/create_window.cc` farbles
only `GetWindowFeaturesFromString()`, so a link or form could place a popup by
real screen coordinates. Dormant behind the `WindowOpenSplitTab` runtime feature
(`status: "test"`).

- [ ] Farble `GetWindowFeaturesFromAttribute()` too (its callers have the
      window), or pin `WindowOpenSplitTab` off
- [ ] Add a farbling browser test for `<a windowfeatures>` once it can be
      enabled

### `TopChromeWebUIProfile`: `SanitizeURL()` uses the frame's profile

The Webium series moves top-chrome WebUIs to a shared `TopChromeWebUIProfile`
and routes user-data decisions to the user's profile through the new
`ContentBrowserClient::GetUserBrowserContext()`
([8fc0aba8fa1a](https://chromium.googlesource.com/chromium/src/+/8fc0aba8fa1a956b5d0e41ffb48c262f1c4a5f8e),
clipboard). `BraveContentBrowserClient::SanitizeURL()`
(`browser/brave_content_browser_client.cc:1761-1766`), called from Brave's
`clipboard_host_impl.cc` shadow, looks up the URL sanitizer service from the
frame's own context and `CHECK`s it. Under the shared profile that's the wrong
profile, and the service may be null. Dormant behind
`kTopChromeWebUISharedRenderer` (disabled).

- [ ] `SanitizeURL()`: look the service up with `GetUserBrowserContext()`, and
      don't `CHECK` it
- [ ] Audit Brave hooks that take the profile from a top-chrome WebUI frame (Tor
      and private checks, prefs), or pin `kTopChromeWebUISharedRenderer` off

### raw_ptr plugin will cover more standard containers

[85345048d28e](https://chromium.googlesource.com/chromium/src/+/85345048d28ee)
and
[637531a326cc](https://chromium.googlesource.com/chromium/src/+/637531a326ccd)
convert `std::vector<T*>` and `std::set<T*>` fields, "preempting an upcoming
clang-plugin update that will strictly ban these". The plugin config didn't
change in the range.

- [ ] `browser/onboarding/onboarding_browsertest.cc:117,120`:
      `std::set<content::WebContents*>`
- [ ] `browser/ui/views/brave_tooltips/brave_tooltip_popup_handler.cc:21`:
      `std::map<std::string, brave_tooltips::BraveTooltipPopup*>`
- [ ] `chromium_src/components/search_engines/brave_template_url_prepopulate_data_unittest.cc:151`:
      `std::vector<const PrepopulatedEngine*>` (static data: `RAW_PTR_EXCLUSION`
      or `raw_ptr`)

### WebUI lint against empty lifecycle overrides and `properties()` getters

[e92d782199aa](https://chromium.googlesource.com/chromium/src/+/e92d782199aa3)
removes them upstream "in preparation for adding an automated check in the WebUI
Eslint plugin". Brave files are linted by upstream's `lint_ts`.

- [ ] `browser/resources/settings/brave_tor_page/brave_tor_snowflake_install_failed_dialog.ts:32`:
      empty `static get properties()`
- [ ] `browser/resources/settings/default_brave_shields_page/components/brave_adblock_editor.ts:45`:
      `override ready() { super.ready() }`

## 3. Code-health migrations

### `WindowOpenDisposition` alias → `ui::mojom::WindowOpenDisposition`

Bug 373551504, 15 scripted commits in the range, e.g.
[a155fd6de230](https://chromium.googlesource.com/chromium/src/+/a155fd6de2300).
`ui/base/window_open_disposition.h` says the alias will be removed once clients
migrate. Qualified uses went from 86 to 522
(`git grep -c 'ui::mojom::WindowOpenDisposition' <tag> -- '*.cc' '*.h' '*.mm'`).
This lift's "IWYU fixes." came from the same campaign.

- [ ] Migrate Brave's 291 unqualified uses in 125 files (7 in `chromium_src`;
      none in patches or plasters):
      `git grep -n -P '(?<!mojom::)\bWindowOpenDisposition\b' -- '*.cc' '*.h' '*.mm'`.
      Upstream's scripts are attached to crbug.com/373551504
- [ ] Drop `ui/base/window_open_disposition.h` includes the migration leaves
      unused

### `base::i18n::GetConfiguredLocale()` → `GetDefaultIcuLocale()`

Bug 542711615, e.g.
[fae0965f7760](https://chromium.googlesource.com/chromium/src/+/fae0965f77607).
Upstream uses went from 33 to 11
(`git grep -c 'GetConfiguredLocale(' <tag> -- '*.cc' '*.mm' '*.h'`). The
replacement returns a `LanguageTag`; use `.tag_string()` for a string. The same
bug's `GetApplicationLocale()` change was fixed in this lift.

- [ ] `browser/brave_vpn/win/brave_vpn_wireguard_service/resources/resource_loader.cc:49`
      (Windows-only, so Linux won't flag it)

### Brave's copy of the deleted `browser_command_proxy.ts`

[e0db4dbfb28f](https://chromium.googlesource.com/chromium/src/+/e0db4dbfb28f4a3941531153f54cd69b7617e2be)
deleted upstream's `browser_command_proxy.ts` for the generated proxies (bug
513276098).
`ui/webui/resources/js/brave_browser_command/brave_browser_command_proxy.ts` is
"based on" it, and the generated `brave_browser_command.mojom-webui.ts` already
exports `browserProxyFactory`.

- [ ] `browser/resources/brave_education/brave_education_app.ts:11,31`: use
      `browserProxyFactory.getInstance().handler`
- [ ] Delete the copy and its `ui/webui/resources/BUILD.gn` entry

## 4. Obsolete Brave code

### Test filters re-enabled by `TEST_F` → `TEST_P`

A negative filter matches the full name exactly, so these now match nothing.

- [ ] `test/filters/browser_tests.filter:1416,2684`:
      `-TabViewTest.IconDataChanged` and
      `-TabViewTest.AlertIndicatorMuteEnabled` → `-All/TabViewTest.<name>/*`
      ([49e98e12f387](https://chromium.googlesource.com/chromium/src/+/49e98e12f387926c9594619b1e4009206d24cc65))
- [ ] `test/filters/unit_tests.filter:1084`: `-ThemeServiceTest.IsGrayscale` →
      `-ThemeServiceTest.IsGrayscale/*` (empty instantiation prefix;
      [e43f201dc450](https://chromium.googlesource.com/chromium/src/+/e43f201dc4509d85165dee0011956a95cc84d3f8))

### Test filters on renamed or deleted suites

- [ ] `test/filters/unit_tests.filter:163,354,355,594`: `ActorTaskListBubble*` →
      `GlicActivityListBubble*`
      ([26f3eadff740](https://chromium.googlesource.com/chromium/src/+/26f3eadff740d1301d56c0cfcb06215209bb6b04))
- [ ] `test/filters/browser_tests.filter:2424`:
      `WebUIReadOnlyOmniboxDragDropBrowserTest.Drop*` →
      `WebUIOmniboxDropBrowserTest.Drop*`
      ([36603cc588ef](https://chromium.googlesource.com/chromium/src/+/36603cc588ef50afc244f937dce5ea91b8d02d65))
- [ ] `test/filters/browser_tests.filter:94`: the suite was renamed
      ([c14e0888d5dc](https://chromium.googlesource.com/chromium/src/+/c14e0888d5dcc1f546329949060a811283a2a2ff)),
      but the test existed at neither tag: delete
- [ ] Delete `browser_tests.filter:1352,1353,1383` (`SyncConfirmationUI*`,
      [6cc582070378](https://chromium.googlesource.com/chromium/src/+/6cc582070378ea7f82f2f7bc5d44edc490913962)),
      `:1255` (`AvatarToolbarButtonSignInBenefits…`,
      [3a520e41da37](https://chromium.googlesource.com/chromium/src/+/3a520e41da378388a3e9b4a87f3c2f9e4d311ba9))
      and `unit_tests.filter:290,291` (`PrivacySandboxAttestations*`,
      [f07765d7d231](https://chromium.googlesource.com/chromium/src/+/f07765d7d231919958ff66b9dd36cb049d3d63b2))
- [ ] `test/filters/generated/`: rerun
      `tools/chromium_tests_analysis/update-upstream-flake-filters.py` (22
      entries on vanished suites, 4 F→P flips, 6 gone tests)

### Filters for flakes upstream fixed

- [ ] `test/filters/base_unittests-linux.filter:19`
      `-TraceEventTestFixture.PrimitiveArgs` (cites crbug.com/325641473): fixed
      at the root by
      [ca6bbb14fd63](https://chromium.googlesource.com/chromium/src/+/ca6bbb14fd63987d1698774485633421d081cc25);
      drop and run on Linux CI
- [ ] `test/filters/components_unittests-mac.filter:10`
      `-VerdictCacheManagerTest.TestCleanUpExpiredVerdict`: upstream fixed a
      32-bit overflow and a seconds truncation
      ([f4af77a6e9ee](https://chromium.googlesource.com/chromium/src/+/f4af77a6e9ee338e15f91c2bea6776bf85c77d15));
      drop and verify on Mac

### Dead overrides and entries

- [ ] `chromium_src/chrome/common/url_constants.h:542,555`:
      `kHistorySearchLearnMorePage{,Managed}URL`, removed upstream
      ([2f8f9b051549](https://chromium.googlesource.com/chromium/src/+/2f8f9b0515493012534cfd11fd530d0fce9d9e70));
      extends M158's dead constants item
- [ ] `browser/resources/settings/br/autofill_section.ts`: targets
      `settings-autofill-section`, renamed to `contact_info_page` in
      153.0.8000.0
      ([bc16334467e7](https://chromium.googlesource.com/chromium/src/+/bc16334467e7e));
      the `contact_info_page` mangler already hides the same card. Delete it,
      its `sources.gni` entry and its import in `br/index.ts` (dead since cr153)
- [ ] `browser/resources/settings/br/config.ts`:
      `RegisterPolymerComponentToIgnore('add-site-dialog')` does nothing, since
      the element is Lit since 157.0.8093.0
      ([057732863da7](https://chromium.googlesource.com/chromium/src/+/057732863da77))
- [ ] `base/compile_overridden_features.inc`:
      `ShowRelatedWebsiteSetsPermissionGrants` isn't a feature at either tag
      (pre-range; M157 lists the other dead names)
- [ ] `kEnforcePrivacySandboxAttestations` pin
      (`rewrite/components/privacy_sandbox/privacy_sandbox_features.cc.yaml`,
      `app/feature_defaults_unittest.cc:296`) gates nothing since
      [f07765d7d231](https://chromium.googlesource.com/chromium/src/+/f07765d7d231919958ff66b9dd36cb049d3d63b2);
      drop both when upstream deletes the feature
- [ ] `components/brave_wallet/browser/network_manager.cc:117-119`: the chain-id
      dump fires only when the major version is 157, so it has collected nothing
      since M158 (added by "[cr157][wallet] Re-enabling the Upper/Lower case
      investigation"; brave-browser#46940)
- [ ] Pre-range: 36 prefixed filter entries name `_F` tests and 27 unprefixed
      ones name `_P`-only tests, so they filter nothing (e.g.
      `BackgroundPage/ExtensionPreferenceApiTest.*`,
      `browser_tests-linux.filter:15` `InfoBarUiTest.InvokeUi_bad_flags`). Use
      the macro index of both tags to list them

## 5. Optional

- [ ] Pin `kCrossDeviceTabsInAppMenu` off or adopt it: the new "Other device
      tabs" submenu
      ([bcaea8aa0111](https://chromium.googlesource.com/chromium/src/+/bcaea8aa011163373407cda07b952ac70051ddc7))
      is upstream's class, next to Brave's `BraveRecentTabsSubMenuModel`
- [ ] `chromium_src/chrome/browser/ui/views/toolbar/pinned_action_toolbar_button.cc`:
      `#define UpdateIcon UpdateIcon_ChromiumImpl` now also rewrites the new
      internal call in `SetEngagedIndicatorStyle()`
      ([f25164af6565](https://chromium.googlesource.com/chromium/src/+/f25164af6565e91b6bfc97b7b527474cb88d1b0f)),
      skipping Brave's override; only reached with `kContextualTasks`, which is
      pinned off. Move it to `make_virtual`
- [ ] Pin `WebGLOnWebGPU` off in the json5 plaster, or farble
      `WebGLRenderingContextWebGPUBase`, which implements `getParameter()` and
      `readPixels()` itself (pre-range; extended by
      [53d3725af115](https://chromium.googlesource.com/chromium/src/+/53d3725af115))
- [ ] Pin `kAndroidNewTabButtonTabstripWebUI` off or adopt it: Android phones
      now build the WebUI tab strip new tab button
      ([82d710072796](https://chromium.googlesource.com/chromium/src/+/82d710072796)),
      which Brave doesn't customize
- [ ] Decide on `kOmniboxVoicePlateIntent`
      ([ea869abfaadf](https://chromium.googlesource.com/chromium/src/+/ea869abfaadfd)):
      the omnibox, fakebox and toolbar mics would launch the Google app's Voice
      Plate; pinning it off needs a C++ plaster and a `BraveCachedFlag` override
- [ ] Pin `kPrewarm` off (covers both triggers, and the omnibox patch hunk can
      go) or `kPrewarmPageLoadAndTabSwitchAfterPaintTrigger`: `PrewarmTabHelper`
      ([ef363587955a](https://chromium.googlesource.com/chromium/src/+/ef363587955a8a2807d29532856f21cf45a1932d))
      prewarms `google.com/search/warmup.html` on page load and tab switch when
      Google is the default search engine, bypassing Brave's
      `StartZeroSuggestPrefetch` block; the trigger is disabled by default
- [ ] `chromium_src/components/content_settings/core/browser/content_settings_registry.cc:334-358`:
      drop Brave's `TOP_LEVEL_STORAGE_ACCESS` registration when upstream removes
      the type; it now clears the type's prefs on startup
      ([57eadefe9846](https://chromium.googlesource.com/chromium/src/+/57eadefe9846cbd4b2f60543b2883c17629e2938))
- [ ] Hand-written Mojo WebUI proxies: 12 more Brave files call
      `XFactory.getRemote()` by hand (`brave_education_proxy.ts`,
      `search_box_proxy.ts`, `brave_new_tab_ui/api/background.ts`, playlist,
      Shields, Speedreader, PSST, VPN, wallet panel, welcome page); move them to
      the generated `browserProxyFactory` as they're touched
- [ ] Stale comments: the `GlicEnabling.java.yaml` description names
      `isPolicyEnforced` (removed by
      [57cbf889fe97](https://chromium.googlesource.com/chromium/src/+/57cbf889fe97e));
      the M157 item to add `isEnabledAndConsentForProfile` and
      `shouldShowExperimentalTriggeringToggle` is still open.
      `browser/ui/views/frame/brave_browser_view.cc:431` cites `kHostViewKey`,
      removed by
      [c300b58b9f1b](https://chromium.googlesource.com/chromium/src/+/c300b58b9f1b0)
      (the reorder is still needed)

## For privacy review

- Web Install API (`navigator.install()`) and the `<install>` element ship on
  desktop
  ([7a105a8919df](https://chromium.googlesource.com/chromium/src/+/7a105a8919df31849bade29703cf5aa7a9c8f1d6)),
  unpinned
- Glic warming enabled by default on Mac (`kGlicWarming`), gated on Glic
  eligibility
- `PrewarmTabHelper` default search engine prewarm (Optional above)
- Google app Voice Plate for the Android omnibox mic (Optional above)
- New `actor_file_upload_tool` traffic annotation (Upcoming deprecations above)

## Tooling TODOs

### `autolift.py build-summary` misses static-analysis and warning failures

Error-prone, NullAway and TraceReferences failures exit because the step wrote
to stderr, and `build-summary` reports "Distinct errors (0)". cr159 needed the
log read by hand for each Android round. GN's "Build argument has no effect"
warning, which flagged the dead `android_override_version_name` in the first
Android round, wasn't surfaced at all.

- [ ] Report `warning: [Check]` lines and the TraceReferences "Missing method"
      lines of a failed step as its errors
- [ ] Report GN "Build argument has no effect" warnings, for Brave-set args

### `changeMethodOwner` matches by name only

The bytecode `changeMethodOwner` redirect rewrote upstream's new instance method
`TabBrowserControlsConstraintsHelper.getObservableConstraints()` along with the
static one Brave meant, and only TraceReferences caught it.

- [ ] Let `changeMethodOwner` take a descriptor (or static-only), and use it for
      existing redirects of overloaded names

### Plaster line rewriters can't be scoped to a function

`add_before_line`/`add_after_line` match a line anywhere in the file. An
insertion next to a generic line (`DUMP_WILL_BE_NOTREACHED()`) needs a `DOTALL`
regex from the function's definition instead (cr159:
`searchbox_handler.cc.yaml`).

- [ ] Add a `function_name` scope to `add_before_line` and `add_after_line`
- [ ] `add_to_public` (and the other member-adding rewriters) indent every line
      of `code`, preprocessor directives included, so `#if`/`#endif` land at the
      member column (cr159: `script_fetch_options.h.yaml`). Keep directives at
      column 0, on master: only the C++ callers of `_indent_code` (GN's
      `append_to_target` uses it too, where `#` starts a comment), and
      regenerate `hover_card_anchor_target.h`, `gpu_process_host.h` and
      `script_fetch_options.h`, the plasters it changes
- [ ] Add a `ts` rewriter that appends members to a class body (cr159: the
      `TestTabSearchApiProxy` stubs in `test_tab_search_api_proxy.ts.yaml`
      needed a `DOTALL` regex up to the class's closing brace)

### `follow-renames` formats unrelated files

Its `pnpm run format` step reflowed `tools/cr/M158_codehealth.md`, which the
rename didn't touch.

- [ ] Format only the files `follow-renames` changed
