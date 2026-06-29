// ESLint flat config for eLibrary Manager frontend.
// The codebase is vanilla ES2015+ (browser globals), served as plain <script>
// tags today and migrating to ES modules + esbuild. This config enforces
// modern, safe patterns without forcing a framework rewrite.
import globals from "globals";

import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    files: ["static/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script", // current monoliths are classic scripts, not modules yet
      globals: {
        ...globals.browser,
        // App-level globals exposed by the existing monoliths.
        IcecreamReader: "readonly",
        LibraryApp: "readonly",
        TTSEngine: "readonly",
      },
    },
    rules: {
      // Encourage modern syntax (aligned with project's "favor modern" rule).
      "prefer-const": "error",
      "no-var": "error",
      "prefer-arrow-callback": "warn",
      "prefer-template": "warn",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-constant-binary-expression": "error",
      eqeqeq: ["error", "smart"],
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    },
  },
  {
    // New ES-module helpers under lib/ opt into module mode.
    files: ["static/js/lib/**/*.js"],
    languageOptions: {
      sourceType: "module",
      ecmaVersion: 2022,
      globals: { ...globals.browser },
    },
    rules: {
      "no-console": ["warn", { allow: ["warn", "error"] }],
      eqeqeq: ["error", "smart"],
    },
  },
  {
    ignores: ["static/js/**/*.min.js", "node_modules/", "dist/"],
  },
];
