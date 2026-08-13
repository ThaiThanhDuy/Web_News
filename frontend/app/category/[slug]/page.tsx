import { notFound } from "next/navigation";
import { SatelliteDish } from "lucide-react";

import { Feed } from "@/components/feed";
import { getArticles, getCategories } from "@/lib/api";

const PAGE_SIZE = 10;

export async function generateStaticParams() {
  const categories = await getCategories();
  return categories.map((c) => ({ slug: c.slug }));
}

export default async function CategoryPage({ params }: { params: { slug: string } }) {
  const categories = await getCategories();
  const current = categories.find((c) => c.slug === params.slug);

  if (categories.length > 0 && !current) {
    notFound();
  }

  const feedPage = await getArticles({
    category: params.slug,
    sort: "feed",
    page: 1,
    pageSize: PAGE_SIZE,
  });

  return (
    <div className="space-y-6">
      {feedPage.items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border py-24 text-center text-muted-foreground">
          <SatelliteDish className="h-8 w-8 text-muted-foreground/50" />
          <p className="font-semibold text-foreground">Chưa có tin nào trong chuyên mục này.</p>
        </div>
      ) : (
        <div className="mx-auto max-w-2xl">
          <Feed
            initialItems={feedPage.items}
            initialPage={1}
            pageSize={PAGE_SIZE}
            initialHasMore={feedPage.has_more}
            category={params.slug}
          />
        </div>
      )}
    </div>
  );
}
