import { useCallback, useEffect, useState } from "react";
import { KeyRound, Plus, Save, Trash2 } from "lucide-react";
import { bridgeCall } from "@/shared/bridge/client";
import { useUIStore } from "@/shared/uiStore";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/shared/i18n";

type Profile = { id: string; name: string; base_url: string; model_id: string; timeout_seconds: number; hasKey: boolean };
const emptyForm = { name: "", baseUrl: "", modelId: "", timeoutSeconds: 30, apiKey: "", clearKey: false };

export function Settings({ backendReady }: { backendReady: boolean }) {
  const t = useT();
  const theme = useUIStore((state) => state.theme);
  const setTheme = useUIStore((state) => state.setTheme);
  const language = useUIStore((state) => state.language);
  const setLanguage = useUIStore((state) => state.setLanguage);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => {
    if (!backendReady) return;
    try { setProfiles((await bridgeCall<{ profiles: Profile[] }>("provider.list")).profiles); }
    catch { setMessage("Could not load provider profiles."); }
  }, [backendReady]);
  useEffect(() => { void refresh(); }, [refresh]);

  function edit(profile: Profile) {
    setSelectedId(profile.id);
    setForm({ name: profile.name, baseUrl: profile.base_url, modelId: profile.model_id,
      timeoutSeconds: profile.timeout_seconds, apiKey: "", clearKey: false });
    setMessage("");
  }
  async function save() {
    setBusy(true); setMessage("");
    try {
      const result = await bridgeCall<{ profile: Profile }>("provider.save", {
        name: form.name, baseUrl: form.baseUrl, modelId: form.modelId,
        timeoutSeconds: Number(form.timeoutSeconds), profileId: selectedId,
        apiKey: form.clearKey ? "" : form.apiKey ? form.apiKey : null,
      });
      setForm((current) => ({ ...current, apiKey: "", clearKey: false }));
      setSelectedId(result.profile.id);
      await refresh(); setMessage("Provider profile saved locally. API keys are stored in Windows Credential Manager.");
    } catch { setMessage("Could not save the profile. Check the URL, model ID, and timeout."); }
    finally { setBusy(false); }
  }
  async function remove(profile: Profile) {
    if (!window.confirm(t("Delete provider profile {name}?", { name: profile.name }))) return;
    setBusy(true); setMessage("");
    try {
      await bridgeCall("provider.delete", { profileId: profile.id });
      setSelectedId(null); setForm(emptyForm); await refresh(); setMessage("Provider profile deleted.");
    } catch { setMessage("Could not delete this profile."); }
    finally { setBusy(false); }
  }

  return <section className="page settings-page" aria-labelledby="settings-heading">
    <div className="eyebrow">{t("PREFERENCES")}</div><h1 id="settings-heading">{t("Settings")}</h1><p>{t("Appearance and optional providers for meetings you explicitly allow to leave this device.")}</p>
    <div className="settings-grid"><Card className="panel setting-card" aria-labelledby="appearance-heading"><h2 id="appearance-heading">{t("Appearance")}</h2>
      <p>{t("Choose the theme used by this desktop app.")}</p><div className="theme-choices" role="group" aria-label={t("Theme")}>
        <Button variant={theme === "dark" ? "default" : "secondary"} aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}>{t("Dark")}</Button>
        <Button variant={theme === "light" ? "default" : "secondary"} aria-pressed={theme === "light"} onClick={() => setTheme("light")}>{t("Light")}</Button>
      </div>
      <p>{t("Interface language")}</p><div className="theme-choices" role="group" aria-label={t("Interface language")}>
        <Button variant={language === "en" ? "default" : "secondary"} aria-pressed={language === "en"} onClick={() => setLanguage("en")}>English</Button>
        <Button variant={language === "vi" ? "default" : "secondary"} aria-pressed={language === "vi"} onClick={() => setLanguage("vi")}>Tiếng Việt</Button>
      </div></Card>
      <Card className="panel setting-card" aria-labelledby="privacy-heading"><h2 id="privacy-heading">{t("Privacy default")}</h2>
        <p>{t("Every new meeting starts as")} <strong>{t("Local Only")}</strong>. {t("Cloud processing remains optional and requires a preview for each send.")}</p>
      </Card></div>
    <div className="settings-section"><div className="settings-section-heading"><div><h2>{t("Provider profiles")}</h2>
      <p>{t("Provider requests are available only for meetings marked Cloud Allowed.")}</p></div>
      <Button variant="secondary" size="sm" onClick={() => { setSelectedId(null); setForm(emptyForm); }}><Plus size={15} /> {t("New profile")}</Button></div>
      <div className="settings-grid"><Card className="panel profile-list">
        {profiles.length === 0 && <p>{t("No provider profiles. Offline minutes still work.")}</p>}
        {profiles.map((profile) => <div className={`profile-row ${profile.id === selectedId ? "selected" : ""}`} key={profile.id}>
          <button onClick={() => edit(profile)}><strong>{profile.name}</strong><small>{profile.base_url} · {profile.model_id}</small></button>
          <span title={t(profile.hasKey ? "API key saved" : "No API key")}><KeyRound size={15} /></span>
          <Button variant="ghost" size="icon-sm" aria-label={t("Delete {name}", { name: profile.name })} disabled={busy} onClick={() => void remove(profile)}><Trash2 size={16} /></Button>
        </div>)}</Card>
        <form className="panel profile-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <h2>{t(selectedId ? "Edit profile" : "New profile")}</h2>
          <Label htmlFor="provider-name">{t("Name")}</Label><Input id="provider-name" required maxLength={120} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          <Label htmlFor="provider-url">{t("Base URL")}</Label><Input id="provider-url" required type="url" value={form.baseUrl} placeholder="https://provider.example/v1" onChange={(event) => setForm({ ...form, baseUrl: event.target.value })} />
          <Label htmlFor="provider-model">{t("Model ID")}</Label><Input id="provider-model" required value={form.modelId} onChange={(event) => setForm({ ...form, modelId: event.target.value })} />
          <Label htmlFor="provider-timeout">{t("Timeout (seconds)")}</Label><Input id="provider-timeout" type="number" min={1} max={600} value={form.timeoutSeconds} onChange={(event) => setForm({ ...form, timeoutSeconds: Number(event.target.value) })} />
          <Label htmlFor="provider-key">{t("API key")} {selectedId && <span className="hint">{t("Leave blank to keep the saved key")}</span>}</Label>
          <Input id="provider-key" type="password" autoComplete="off" value={form.apiKey} disabled={form.clearKey} onChange={(event) => setForm({ ...form, apiKey: event.target.value })} />
          {profiles.find((profile) => profile.id === selectedId)?.hasKey && <div className="checkbox-label"><Switch id="remove-key" checked={form.clearKey}
            onCheckedChange={(checked) => setForm({ ...form, clearKey: checked, apiKey: "" })} /><Label htmlFor="remove-key">{t("Remove saved key")}</Label></div>}
          <p className="hint">{t("Saved keys are never displayed. Local providers may not need one.")}</p>
          <Button disabled={busy || !backendReady} type="submit"><Save size={15} /> {t("Save profile")}</Button>
        </form></div>
      {message && <p className="feedback" role="status">{t(message)}</p>}</div>
  </section>;
}
