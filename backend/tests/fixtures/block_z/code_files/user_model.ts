/**
 * User model for type-safe user operations.
 */
export interface User {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  createdAt: Date;
  updatedAt: Date;
  isActive: boolean;
}

export interface CreateUserDTO {
  email: string;
  password: string;
  firstName: string;
  lastName: string;
}

export interface UpdateUserDTO {
  email?: string;
  firstName?: string;
  lastName?: string;
  isActive?: boolean;
}

export class UserModel {
  private users: Map<string, User> = new Map();

  /**
   * Create a new user.
   */
  async create(dto: CreateUserDTO): Promise<User> {
    const user: User = {
      id: this.generateId(),
      email: dto.email,
      firstName: dto.firstName,
      lastName: dto.lastName,
      createdAt: new Date(),
      updatedAt: new Date(),
      isActive: true
    };
    
    this.users.set(user.id, user);
    return user;
  }

  /**
   * Find a user by ID.
   */
  async findById(id: string): Promise<User | null> {
    return this.users.get(id) || null;
  }

  /**
   * Find a user by email.
   */
  async findByEmail(email: string): Promise<User | null> {
    for (const user of this.users.values()) {
      if (user.email === email) {
        return user;
      }
    }
    return null;
  }

  /**
   * Update a user.
   */
  async update(id: string, dto: UpdateUserDTO): Promise<User | null> {
    const user = this.users.get(id);
    if (!user) return null;
    
    const updatedUser: User = {
      ...user,
      ...dto,
      updatedAt: new Date()
    };
    
    this.users.set(id, updatedUser);
    return updatedUser;
  }

  /**
   * Delete a user.
   */
  async delete(id: string): Promise<boolean> {
    return this.users.delete(id);
  }

  private generateId(): string {
    return `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}
