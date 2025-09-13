from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

@dataclass
class Chunk:
    text: str
    chunk_idx: int
    metadata: Dict[str, Any]
    is_header: bool = False
    is_table: bool = False
    parent_section: str = ""

class AdaptiveChunker:
    """
    Adaptive text chunking that preserves structure and context
    """
    
    def __init__(self, max_chars: int = 1200, overlap: int = 100):
        self.max_chars = max_chars
        self.overlap = overlap
        
        # Patterns for structure detection
        self.header_patterns = [
            r'^#{1,6}\s+.+',  # Markdown headers
            r'^\d+\.\s+.+',   # Numbered lists
            r'^[A-Z][A-Z\s]+$',  # ALL CAPS headers
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*:$',  # Title Case headers
        ]
        
        self.section_patterns = [
            r'^(?:Chapter|Section|Part)\s+\d+',  # Chapter markers
            r'^\d+\.\d+',  # Subsection numbers
            r'^[IVX]+\.',  # Roman numerals
        ]
        
        self.table_indicators = [
            r'^\s*\|.*\|',  # Markdown tables
            r'^\s*\w+\s+\w+\s+\w+',  # Space-separated columns
            r'^\s*\w+,\s*\w+',  # CSV-like data
        ]

    def chunk_text(self, text: str, document_meta: Dict[str, Any] = None) -> List[Chunk]:
        """
        Chunk text while preserving structure
        """
        if not text.strip():
            return []
        
        # Detect document structure
        structure = self._analyze_structure(text)
        
        # Create chunks based on structure
        chunks = []
        current_chunk = ""
        current_metadata = {}
        chunk_idx = 0
        
        lines = text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if this is a structural element
            if self._is_header(line):
                # Save current chunk if it exists
                if current_chunk.strip():
                    chunks.append(Chunk(
                        text=current_chunk.strip(),
                        chunk_idx=chunk_idx,
                        metadata=current_metadata.copy(),
                        is_header=False,
                        is_table=self._is_table(current_chunk),
                        parent_section=current_metadata.get('section', '')
                    ))
                    chunk_idx += 1
                    current_chunk = ""
                
                # Start new chunk with header
                header_chunk = self._create_header_chunk(line, i, lines, chunk_idx)
                chunks.append(header_chunk)
                chunk_idx += 1
                
                # Set metadata for following chunks
                current_metadata = {
                    'section': line,
                    'header_line': i,
                    'document_meta': document_meta or {}
                }
                
            elif self._is_table_start(line):
                # Handle table as separate chunk
                table_chunk = self._extract_table_chunk(lines, i, chunk_idx, current_metadata)
                if table_chunk:
                    chunks.append(table_chunk)
                    chunk_idx += 1
                    i = table_chunk.metadata.get('end_line', i)
            
            else:
                # Regular text line
                if len(current_chunk + line) > self.max_chars:
                    # Save current chunk
                    if current_chunk.strip():
                        chunks.append(Chunk(
                            text=current_chunk.strip(),
                            chunk_idx=chunk_idx,
                            metadata=current_metadata.copy(),
                            is_header=False,
                            is_table=self._is_table(current_chunk),
                            parent_section=current_metadata.get('section', '')
                        ))
                        chunk_idx += 1
                    
                    # Start new chunk with overlap
                    current_chunk = self._create_overlap(current_chunk) + line
                else:
                    current_chunk += '\n' + line if current_chunk else line
            
            i += 1
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(Chunk(
                text=current_chunk.strip(),
                chunk_idx=chunk_idx,
                metadata=current_metadata.copy(),
                is_header=False,
                is_table=self._is_table(current_chunk),
                parent_section=current_metadata.get('section', '')
            ))
        
        # Apply overlap between chunks
        return self._apply_overlap(chunks)

    def _analyze_structure(self, text: str) -> Dict[str, Any]:
        """Analyze document structure"""
        lines = text.split('\n')
        
        structure = {
            'headers': [],
            'sections': [],
            'tables': [],
            'lists': []
        }
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            if self._is_header(line):
                structure['headers'].append({'line': i, 'text': line})
            elif self._is_section(line):
                structure['sections'].append({'line': i, 'text': line})
            elif self._is_table_start(line):
                structure['tables'].append({'line': i, 'text': line})
        
        return structure

    def _is_header(self, line: str) -> bool:
        """Check if line is a header"""
        for pattern in self.header_patterns:
            if re.match(pattern, line):
                return True
        return False

    def _is_section(self, line: str) -> bool:
        """Check if line is a section marker"""
        for pattern in self.section_patterns:
            if re.match(pattern, line):
                return True
        return False

    def _is_table_start(self, line: str) -> bool:
        """Check if line starts a table"""
        for pattern in self.table_indicators:
            if re.match(pattern, line):
                return True
        return False

    def _is_table(self, text: str) -> bool:
        """Check if text contains table data"""
        lines = text.split('\n')
        table_lines = 0
        
        for line in lines:
            if self._is_table_start(line):
                table_lines += 1
        
        return table_lines >= 2  # At least 2 table lines

    def _create_header_chunk(self, header: str, line_idx: int, lines: List[str], chunk_idx: int) -> Chunk:
        """Create a chunk for a header with some following context"""
        # Include a few lines after header for context
        context_lines = []
        for i in range(line_idx + 1, min(line_idx + 3, len(lines))):
            if lines[i].strip():
                context_lines.append(lines[i])
                break
        
        text = header
        if context_lines:
            text += '\n' + '\n'.join(context_lines)
        
        return Chunk(
            text=text,
            chunk_idx=chunk_idx,
            metadata={
                'is_header': True,
                'header_line': line_idx,
                'header_text': header
            },
            is_header=True,
            is_table=False,
            parent_section=""
        )

    def _extract_table_chunk(self, lines: List[str], start_idx: int, chunk_idx: int, metadata: Dict) -> Chunk:
        """Extract a complete table as a chunk"""
        table_lines = []
        i = start_idx
        
        # Collect table lines
        while i < len(lines):
            line = lines[i].strip()
            if self._is_table_start(line) or (table_lines and line and not line.startswith(' ')):
                table_lines.append(line)
            elif not line and table_lines:
                # Empty line might end table
                break
            elif not table_lines:
                # No table started yet
                break
            else:
                table_lines.append(line)
            i += 1
        
        if len(table_lines) >= 2:
            return Chunk(
                text='\n'.join(table_lines),
                chunk_idx=chunk_idx,
                metadata={
                    **metadata,
                    'is_table': True,
                    'table_lines': len(table_lines),
                    'start_line': start_idx,
                    'end_line': i
                },
                is_header=False,
                is_table=True,
                parent_section=metadata.get('section', '')
            )
        
        return None

    def _create_overlap(self, text: str) -> str:
        """Create overlap text from the end of current chunk"""
        if not text:
            return ""
        
        # Take last few sentences or words
        sentences = re.split(r'[.!?]+', text)
        if len(sentences) > 1:
            # Take last sentence
            return sentences[-2].strip() + " "
        else:
            # Take last few words
            words = text.split()
            if len(words) > 10:
                return ' '.join(words[-10:]) + " "
            return text[-self.overlap:] + " " if len(text) > self.overlap else text

    def _apply_overlap(self, chunks: List[Chunk]) -> List[Chunk]:
        """Apply overlap between chunks"""
        if len(chunks) <= 1:
            return chunks
        
        result = []
        
        for i, chunk in enumerate(chunks):
            if i > 0:
                # Add overlap from previous chunk
                prev_chunk = result[-1]
                overlap_text = self._create_overlap(prev_chunk.text)
                
                if overlap_text:
                    chunk.text = overlap_text + chunk.text
                    chunk.metadata['has_overlap'] = True
                    chunk.metadata['overlap_from'] = i - 1
            
            result.append(chunk)
        
        return result

def chunk_text_adaptive(text: str, max_chars: int = 1200, overlap: int = 100, document_meta: Dict[str, Any] = None) -> List[Chunk]:
    """
    Convenience function for adaptive chunking
    """
    chunker = AdaptiveChunker(max_chars=max_chars, overlap=overlap)
    return chunker.chunk_text(text, document_meta)
