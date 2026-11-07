import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { NativeSelect } from "@/components/ui/select";
import { api } from "@/lib/api";
import { when } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";

/** Selects the active competition; defaults to the most recent one. Returns the active id. */
export function useActiveCompetition() {
  const ws = useWorkspace();
  const list = useQuery({ queryKey: ["competitions"], queryFn: api.listCompetitions });
  useEffect(() => {
    if (!list.data) return;
    if (!ws.competitionId || !list.data.some((c) => c.id === ws.competitionId)) {
      if (list.data[0]) ws.set({ competitionId: list.data[0].id });
    }
  }, [list.data, ws]);
  return { id: ws.competitionId, list };
}

export function CompetitionPicker() {
  const ws = useWorkspace();
  const { id, list } = useActiveCompetition();
  if (!list.data?.length) return null;
  return (
    <NativeSelect
      aria-label="Competition run"
      className="w-80"
      value={id ?? ""}
      onChange={(e) => ws.set({ competitionId: e.target.value })}
    >
      {list.data.map((c) => (
        <option key={c.id} value={c.id}>
          {c.document_name} — {when(c.created_at)} ({c.status.replace(/_/g, " ")})
        </option>
      ))}
    </NativeSelect>
  );
}

export function RequirementPicker() {
  const ws = useWorkspace();
  const list = useQuery({ queryKey: ["requirements"], queryFn: api.listRequirements });
  if (!list.data?.length) return null;
  return (
    <NativeSelect
      aria-label="Requirement workbook"
      className="w-72"
      value={ws.requirementId ?? ""}
      onChange={(e) => ws.set({ requirementId: e.target.value, promptRunId: null })}
    >
      <option value="" disabled>
        Choose a workbook
      </option>
      {list.data.map((r) => (
        <option key={r.id} value={r.id}>
          {r.filename} — {r.field_count} fields, {when(r.created_at)}
        </option>
      ))}
    </NativeSelect>
  );
}
