import { isAxiosError } from "axios";
import { apiClient } from "@/apis/client";
import type { CurrentUser } from "@/types/responses/auth";

export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    const response = await apiClient.get<CurrentUser>("/me");
    return response.data;
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 401) {
      return null;
    }
    throw error;
  }
}
