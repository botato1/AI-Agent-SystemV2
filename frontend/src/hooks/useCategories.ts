import { useCallback, useEffect, useState } from "react";
import {
  Category,
  getCategoryListApi,
  createCategoryApi,
  updateCategoryApi,
  deleteCategoryApi,
} from "../services/category";

const RECENT_CATEGORY_KEY_PREFIX = "recent_category_id_";

function getRecentCategoryId(workspaceId: string): string | null {
  return localStorage.getItem(RECENT_CATEGORY_KEY_PREFIX + workspaceId);
}

function setRecentCategoryId(workspaceId: string, categoryId: string) {
  localStorage.setItem(RECENT_CATEGORY_KEY_PREFIX + workspaceId, categoryId);
}

export function useCategories(workspaceId: string) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    const res = await getCategoryListApi(workspaceId);
    if (res.status === "success") {
      setCategories([...res.categories].sort((a, b) => a.display_order - b.display_order));
      setErrorMessage(null);
    } else {
      setErrorMessage(res.message);
    }
    setIsLoading(false);
  }, [workspaceId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  async function createCategory(name: string): Promise<Category | null> {
    const res = await createCategoryApi(workspaceId, name);
    if (res.status === "success" && res.category) {
      setCategories((prev) => [...prev, res.category as Category]);
      return res.category;
    }
    setErrorMessage(res.message);
    return null;
  }

  async function renameCategory(categoryId: string, name: string): Promise<boolean> {
    const res = await updateCategoryApi(categoryId, { name });
    if (res.status === "success" && res.category) {
      setCategories((prev) => prev.map((c) => (c.id === categoryId ? (res.category as Category) : c)));
      return true;
    }
    setErrorMessage(res.message);
    return false;
  }

  async function reorderCategory(categoryId: string, displayOrder: number): Promise<boolean> {
    const res = await updateCategoryApi(categoryId, { display_order: displayOrder });
    if (res.status === "success" && res.category) {
      setCategories((prev) =>
        [...prev.map((c) => (c.id === categoryId ? (res.category as Category) : c))].sort(
          (a, b) => a.display_order - b.display_order
        )
      );
      return true;
    }
    setErrorMessage(res.message);
    return false;
  }

  async function deleteCategory(categoryId: string): Promise<boolean> {
    const res = await deleteCategoryApi(categoryId);
    if (res.status === "success") {
      setCategories((prev) => prev.filter((c) => c.id !== categoryId));
      return true;
    }
    setErrorMessage(res.message);
    return false;
  }

  const defaultCategory = categories.find((c) => c.is_default) ?? null;
  const recentCategoryId = getRecentCategoryId(workspaceId);
  // 최근 쓴 카테고리가 삭제됐거나 기록이 없으면 기본 카테고리로 떨어진다.
  const suggestedCategoryId =
    (recentCategoryId && categories.some((c) => c.id === recentCategoryId) ? recentCategoryId : null) ??
    defaultCategory?.id ??
    null;

  return {
    categories,
    isLoading,
    errorMessage,
    defaultCategory,
    suggestedCategoryId,
    refetch,
    createCategory,
    renameCategory,
    reorderCategory,
    deleteCategory,
    markCategoryUsed: (categoryId: string) => setRecentCategoryId(workspaceId, categoryId),
  };
}
