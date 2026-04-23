import { gatewayFetch } from "../lib/gateway-client.js";
import { clearNotice, renderRemoteList, setBusy, setOptionsBadge, showNotice, showOptionsApp, showOptionsMissing } from "./render.js";

export function createOptionsActions(state, elements) {
  return {
    async boot() {
      await this.refreshGateway();
    },

    async refreshGateway() {
      setBusy(elements, state, true);
      clearNotice(elements);
      setOptionsBadge(elements, "checking", "Checking...");
      try {
        await gatewayFetch("/healthz");
        setOptionsBadge(elements, "ready", "Gateway Ready");
        showOptionsApp(elements);
        await this.loadRemotes();
      } catch (_error) {
        setOptionsBadge(elements, "missing", "Gateway Missing");
        showOptionsMissing(elements);
        showNotice(elements, "Gateway 没响应。先在终端执行 `coco-flow gateway start -d`。", "warning");
      } finally {
        setBusy(elements, state, false);
      }
    },

    async loadRemotes() {
      try {
        elements.message.textContent = "Loading remotes…";
        const payload = await gatewayFetch("/remote/list");
        const remotes = Array.isArray(payload.remotes) ? payload.remotes : [];
        renderRemoteList(elements, remotes, async (name) => this.deleteRemote(name));
      } catch (error) {
        elements.message.textContent = "Failed to load remotes.";
        showNotice(elements, error.message, "error");
      }
    },

    async createRemote() {
      setBusy(elements, state, true);
      clearNotice(elements);
      try {
        const formData = new FormData(elements.form);
        const payload = {
          name: String(formData.get("name") || "").trim(),
          host: String(formData.get("host") || "").trim(),
          user: String(formData.get("user") || "").trim(),
          local_port: Number(formData.get("local_port") || 4318),
          remote_port: Number(formData.get("remote_port") || 4318),
        };
        await gatewayFetch("/remote", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        elements.form.reset();
        elements.form.local_port.value = "4318";
        elements.form.remote_port.value = "4318";
        showNotice(elements, `Saved remote ${payload.name}.`, "success");
        await this.loadRemotes();
      } catch (error) {
        showNotice(elements, error.message, "error");
      } finally {
        setBusy(elements, state, false);
      }
    },

    async deleteRemote(name) {
      if (!name) {
        return;
      }
      setBusy(elements, state, true);
      clearNotice(elements);
      try {
        await gatewayFetch(`/remote/${encodeURIComponent(name)}`, { method: "DELETE" });
        showNotice(elements, `Deleted remote ${name}.`, "success");
        await this.loadRemotes();
      } catch (error) {
        showNotice(elements, error.message, "error");
      } finally {
        setBusy(elements, state, false);
      }
    },
  };
}
