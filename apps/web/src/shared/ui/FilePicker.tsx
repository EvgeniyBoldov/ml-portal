import React, { useRef, useState } from 'react';
import Button from './Button';
import styles from './FilePicker.module.css';

type Props = {
  onFileSelected: (file: File | null) => void;
  accept?: string;
  disabled?: boolean;
  label?: string;
  selectedFile?: File | null;
};

export default function FilePicker({
  onFileSelected,
  accept,
  disabled,
  label = 'Choose file',
  selectedFile,
}: Props) {
  const ref = useRef<HTMLInputElement>(null);
  
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    onFileSelected(file);
  };

  return (
    <div className={styles.wrap}>
      <input
        ref={ref}
        type="file"
        className={styles.inputHidden}
        accept={accept}
        onChange={handleFileChange}
        disabled={disabled}
      />
      <Button onClick={() => ref.current?.click()} disabled={disabled}>
        {label}
      </Button>
      {selectedFile && (
        <div className={styles.fileInfo}>
          <span className={styles.fileName}>{selectedFile.name}</span>
          <span className={styles.fileSize}>
            ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
          </span>
        </div>
      )}
    </div>
  );
}
