import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { SidebarLayout } from "@/components/research/SidebarLayout";
import { RegimeDetailScreen } from "@/components/research/RegimeDetailScreen";
import type { Regime } from "@/lib/regimes";

export const Route = createFileRoute("/regimes/$regimeId")({
  component: RegimeDetail,
});

function stubRegime(id: string): Regime {
  return {
    id,
    name: "",
    shortDescription: "",
    confirmed: false,
    summary: "",
    scope: "",
    process: "",
    consequence: "",
    obligations: [],
    guidance: "",
    regulatory_guidance: [],
    regulatory_guidance_updated_at: null,
  };
}

function RegimeDetail() {
  const { regimeId } = Route.useParams();
  const navigate = useNavigate();

  return (
    <SidebarLayout>
      <RegimeDetailScreen
        key={regimeId}
        regime={stubRegime(regimeId)}
        onBack={() => navigate({ to: "/regimes" })}
      />
    </SidebarLayout>
  );
}
