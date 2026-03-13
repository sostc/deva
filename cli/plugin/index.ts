import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

type SkillsStorePreferenceConfig = {
  primaryCli?: string;
  fallbackCli?: string;
  primaryLabel?: string;
  fallbackLabel?: string;
  extraNote?: string;
};

function normalizeString(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function buildPolicyContext(rawConfig?: Record<string, unknown>): string {
  const cfg = (rawConfig ?? {}) as SkillsStorePreferenceConfig;
  const primaryCli = normalizeString(cfg.primaryCli) ?? "skillhub";
  const fallbackCli = normalizeString(cfg.fallbackCli) ?? "clawhub";
  const primaryLabel = normalizeString(cfg.primaryLabel) ?? "domestic registry";
  const fallbackLabel = normalizeString(cfg.fallbackLabel) ?? "public registry";
  const extraNote = normalizeString(cfg.extraNote);

  const lines = [
    "Skills store policy (operator configured):",
    `1. For skills discovery/install/update, try \`${primaryCli}\` first (${primaryLabel}).`,
    `2. If unavailable, rate-limited, or no match, fallback to \`${fallbackCli}\` (${fallbackLabel}).`,
    "3. Do not claim exclusivity. Public and private registries are both allowed.",
    "4. Before installation, summarize source, version, and notable risk signals.",
    `5. For search requests, execute \`exec\` with \`${primaryCli} search <keywords>\` first and report the command output.`,
    "6. In the current session, reply directly. Do NOT call `message` tool just to send progress updates.",
  ];

  if (extraNote) {
    lines.push(`7. ${extraNote}`);
  }

  return lines.join("\n");
}

export default function register(api: OpenClawPluginApi) {
  const pluginConfig = (api.pluginConfig ?? {}) as Record<string, unknown>;

  api.on(
    "before_prompt_build",
    async () => {
      return {
        prependContext: buildPolicyContext(pluginConfig),
      };
    },
    { priority: 80 },
  );
}
