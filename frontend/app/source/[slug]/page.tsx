import { notFound } from "next/navigation";
import { SatelliteDish } from "lucide-react";

import { Feed } from "@/components/feed";
import { getArticles, getSources } from "@/lib/api";

const PAGE_SIZE = 10;

export async function generateStaticParams() {
  const sources = await getSources();
  return sources.map((s) => ({ slug: s.slug }));
}

export default async function SourcePage({ params }: { params: { slug: string } }) {
  const sources = await getSources();
  const current = sources.find((s) => s.slug === params.slug);

  if (sources.length > 0 && !current) {
    notFound();
  }

  const feedPage = await getArticles({
    source: params.slug,
    sort: "feed",
    page: 1,
    pageSize: PAGE_SIZE,
  });

  return (
    <div className="space-y-6">
      {feedPage.items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border py-24 text-center text-muted-foreground">
          <SatelliteDish className="h-8 w-8 text-muted-foreground/50" />
          <p className="font-semibold text-foreground">Chưa có tin nào từ nguồn này.</p>
        </div>
      ) : (
        <div className="mx-auto max-w-2xl">
          <Feed
            initialItems={feedPage.items}
            initialPage={1}
            pageSize={PAGE_SIZE}
            initialHasMore={feedPage.has_more}
            source={params.slug}
          />
        </div>
      )}
    </div>
  );
}
