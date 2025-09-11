import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { vi } from 'vitest'
import ChatTags from '../ChatTags'

// Mock the useChat hook
vi.mock('../../contexts/ChatContext', () => ({
  useChat: () => ({
    updateChatTags: vi.fn()
  })
}))

describe('ChatTags', () => {
  const defaultProps = {
    chatId: 'test-chat-id',
    tags: ['test', 'example'],
    onTagsChange: vi.fn()
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders existing tags', () => {
    render(<ChatTags {...defaultProps} />)
    
    expect(screen.getByText('test')).toBeInTheDocument()
    expect(screen.getByText('example')).toBeInTheDocument()
  })

  it('renders "No tags" when no tags provided', () => {
    render(<ChatTags {...defaultProps} tags={[]} />)
    
    expect(screen.getByText('Нет тегов')).toBeInTheDocument()
  })

  it('opens modal when edit button is clicked', () => {
    render(<ChatTags {...defaultProps} />)
    
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    expect(screen.getByText('Управление тегами')).toBeInTheDocument()
  })

  it('adds new tag when input is filled and add button clicked', async () => {
    render(<ChatTags {...defaultProps} />)
    
    // Open modal
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    // Add new tag
    const input = screen.getByPlaceholderText('Добавить тег...')
    fireEvent.change(input, { target: { value: 'new-tag' } })
    
    const addButton = screen.getByText('Добавить')
    fireEvent.click(addButton)
    
    expect(screen.getByText('new-tag')).toBeInTheDocument()
  })

  it('removes tag when remove button is clicked', () => {
    render(<ChatTags {...defaultProps} />)
    
    // Open modal
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    // Remove tag
    const removeButtons = screen.getAllByText('×')
    fireEvent.click(removeButtons[0]) // Remove first tag
    
    expect(screen.queryByText('test')).not.toBeInTheDocument()
    expect(screen.getByText('example')).toBeInTheDocument()
  })

  it('saves changes when save button is clicked', async () => {
    const onTagsChange = vi.fn()
    render(<ChatTags {...defaultProps} onTagsChange={onTagsChange} />)
    
    // Open modal
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    // Add new tag
    const input = screen.getByPlaceholderText('Добавить тег...')
    fireEvent.change(input, { target: { value: 'new-tag' } })
    
    const addButton = screen.getByText('Добавить')
    fireEvent.click(addButton)
    
    // Save changes
    const saveButton = screen.getByText('Сохранить')
    fireEvent.click(saveButton)
    
    await waitFor(() => {
      expect(onTagsChange).toHaveBeenCalledWith(['test', 'example', 'new-tag'])
    })
  })

  it('cancels changes when cancel button is clicked', () => {
    render(<ChatTags {...defaultProps} />)
    
    // Open modal
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    // Add new tag
    const input = screen.getByPlaceholderText('Добавить тег...')
    fireEvent.change(input, { target: { value: 'new-tag' } })
    
    const addButton = screen.getByText('Добавить')
    fireEvent.click(addButton)
    
    // Cancel changes
    const cancelButton = screen.getByText('Отмена')
    fireEvent.click(cancelButton)
    
    // Modal should be closed and original tags should remain
    expect(screen.queryByText('Управление тегами')).not.toBeInTheDocument()
    expect(screen.getByText('test')).toBeInTheDocument()
    expect(screen.getByText('example')).toBeInTheDocument()
  })

  it('adds tag when Enter key is pressed', () => {
    render(<ChatTags {...defaultProps} />)
    
    // Open modal
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    // Add new tag with Enter key
    const input = screen.getByPlaceholderText('Добавить тег...')
    fireEvent.change(input, { target: { value: 'new-tag' } })
    fireEvent.keyPress(input, { key: 'Enter', code: 'Enter' })
    
    expect(screen.getByText('new-tag')).toBeInTheDocument()
  })

  it('does not add empty tag', () => {
    render(<ChatTags {...defaultProps} />)
    
    // Open modal
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    // Try to add empty tag
    const input = screen.getByPlaceholderText('Добавить тег...')
    fireEvent.change(input, { target: { value: '   ' } })
    
    const addButton = screen.getByText('Добавить')
    expect(addButton).toBeDisabled()
  })

  it('does not add duplicate tag', () => {
    render(<ChatTags {...defaultProps} />)
    
    // Open modal
    const editButton = screen.getByTitle('Управление тегами')
    fireEvent.click(editButton)
    
    // Try to add existing tag
    const input = screen.getByPlaceholderText('Добавить тег...')
    fireEvent.change(input, { target: { value: 'test' } })
    
    const addButton = screen.getByText('Добавить')
    fireEvent.click(addButton)
    
    // Should not add duplicate
    const testTags = screen.getAllByText('test')
    expect(testTags).toHaveLength(1) // Only the original one
  })
})
