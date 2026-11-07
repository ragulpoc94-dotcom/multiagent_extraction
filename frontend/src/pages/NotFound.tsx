import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/common";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <EmptyState
      icon={Compass}
      title="This page doesn't exist"
      body="The address may be mistyped, or the page was moved."
      action={<Button asChild><Link to="/">Go to overview</Link></Button>}
    />
  );
}
