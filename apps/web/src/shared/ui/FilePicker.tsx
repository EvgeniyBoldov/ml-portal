import React, { useRef } from 'react';
import Button from './Button';
import styles from './FilePicker.module.css';

type Props = {
  onFilesSelected: (files: File[]) => void;
  accept?: string;
  disabled?: boolean;
  label?: string;
  multiple?: boolean;
};

export default function FilePicker({
  onFilesSelected,
  accept,
  disabled,
  label = 'Choose file',
  multiple = false,
}: Props) {
  const ref = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (fileList && fileList.length > 0) {
      onFilesSelected(Array.from(fileList));
    }
    // Reset input value so the same file can be selected again if needed
    if (ref.current) {
      ref.current.value = '';
    }
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
        multiple={multiple}
      />
      <Button onClick={() => ref.current?.click()} disabled={disabled}>
        {label}
      </Button>
    </div>
  );
}
