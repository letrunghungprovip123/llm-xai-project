/* LLM-XAI dashboard client-side utilities. */

(function () {
    "use strict";

    const root = window.dash_clientside = window.dash_clientside || {};
    const namespace = root.llm_xai = root.llm_xai || {};
    const supportedLocales = new Set(["vi", "en"]);

    function normalizeLocale(value) {
        const normalized = String(value || "")
            .trim()
            .toLowerCase()
            .replace("_", "-")
            .split("-", 1)[0];
        return supportedLocales.has(normalized) ? normalized : "vi";
    }

    namespace.applyLocaleState = function (value) {
        const locale = normalizeLocale(value);
        document.documentElement.lang = locale;

        document.querySelectorAll("[data-locale-target]").forEach((control) => {
            const active = control.getAttribute("data-locale-target") === locale;
            control.setAttribute("aria-pressed", active ? "true" : "false");
            control.classList.toggle("locale-switch__button--active", active);
        });

        return locale;
    };
})();

(function () {
    "use strict";

    const root = window.dash_clientside = window.dash_clientside || {};
    const namespace = root.llm_xai = root.llm_xai || {};

    namespace.applyDocumentMetadata = function (metadata) {
        if (!metadata || typeof metadata !== "object") {
            return "metadata-missing";
        }
        const lang = metadata.lang === "en" ? "en" : "vi";
        const title = String(metadata.title || "LLM-XAI");
        document.documentElement.lang = lang;
        document.title = title;
        return `${lang}:${title}`;
    };
})();
