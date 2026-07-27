import { useEffect, useState } from "react";
import { RoomFile, getRoomFilesApi, linkRoomFileApi, unlinkRoomFileApi } from "../services/roomFile";
import { uploadDocumentApi } from "../services/document";

// 채팅방에 연결된 실제 문서 파일 목록 관리 (업로드 시 room_id를 같이 보내면 백엔드가 자동으로 연결해줌)
export function useRoomFiles(workspaceId: string, roomId: string) {
  const [files, setFiles] = useState<RoomFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  async function loadFiles() {
    if (!workspaceId || !roomId) return;
    const res = await getRoomFilesApi(workspaceId, roomId);
    if (res.status === "success") {
      setFiles(res.files);
    }
  }

  useEffect(() => {
    setIsLoading(true);
    loadFiles().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, roomId]);

  // 업로드는 문서 처리 서버 응답까지 최대 5분 걸릴 수 있다
  async function uploadFile(file: File): Promise<boolean> {
    setIsUploading(true);
    const res = await uploadDocumentApi(workspaceId, file, roomId);
    setIsUploading(false);

    if (res.status === "success") {
      await loadFiles();
      return true;
    }

    alert(`문서 업로드 실패: ${res.message}`);
    return false;
  }

  async function removeFile(fileId: string) {
    const res = await unlinkRoomFileApi(workspaceId, roomId, fileId);
    if (res.status === "success") {
      setFiles((prev) => prev.filter((f) => f.id !== fileId));
    } else {
      alert(`파일 연결 해제 실패: ${res.message}`);
    }
  }

  // 이미 다른 곳(문서 분석 등)에 업로드된 기존 문서를 이 채팅방에 연결
  async function linkExistingFile(fileId: string): Promise<boolean> {
    const res = await linkRoomFileApi(workspaceId, roomId, fileId);
    if (res.status === "success") {
      await loadFiles();
      return true;
    }
    alert(`파일 연결 실패: ${res.message}`);
    return false;
  }

  return { files, isLoading, isUploading, uploadFile, removeFile, linkExistingFile };
}
